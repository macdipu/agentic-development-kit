"""Cross-agent-platform handoff files, compatible with github.com/ishipu/agent-handoff.

Python-native reimplementation of that project's file format (it is a small,
zero-runtime-dependency Node/TS CLI; rather than add a Node toolchain to this
Python-only kit, its ~5 template functions are ported here directly). Unlike
RuntimeStore's own governance ledger (local, gitignored), these files are
meant to be committed: `.agent/HANDOFF.md` + `.agent/sessions/*.md` are the
plain-text handoff notes any agent platform (Claude Code, Codex, ...) reads
on pickup and writes on close, so a different tool on a different machine can
continue the same work from what's in git -- no server, no shared runtime.

Upstream restricts `agent` to exactly "claude" or "codex"; this module keeps
that restriction so files stay valid input to the real agent-handoff CLI too.

Handoff content is structured (task/completed/changed_files/tests/blockers/
decisions/next_action) rather than one free-form summary string, so a picking-up
agent -- or a script -- can read a specific field instead of parsing prose, and
so a closing agent can't skip a category by writing one vague sentence.
"""
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

VALID_AGENTS = ("claude", "codex")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp_for_filename(ts: str) -> str:
    # 2026-05-13T14:42:35.310000+00:00 -> 2026-05-13T14-42-35-310Z
    dt = datetime.fromisoformat(ts).astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H-%M-%S-") + f"{dt.microsecond // 1000:03d}Z"


def _bullet_list(items: Optional[Iterable[str]]) -> str:
    items = list(items or [])
    return "\n".join(f"- {item}" for item in items) if items else "(none)"


def git_snapshot(repo_root) -> str:
    """Branch, most recent commit, and short status -- the same three facts upstream embeds."""
    root = Path(repo_root)
    def run(*args):
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=10)
        return result.stdout.strip() if result.returncode == 0 else "(unavailable)"
    branch = run("rev-parse", "--abbrev-ref", "HEAD")
    commit = run("log", "-1", "--oneline")
    status = run("status", "--short") or "(clean)"
    return f"Branch: {branch}\nRecent commit: {commit}\nStatus:\n{status}"


def git_user(repo_root) -> str:
    """The configured git identity running this session -- distinct from `agent`
    (claude/codex), since more than one person can drive either platform on a
    shared project. Falls back to whatever half of name/email is configured."""
    root = Path(repo_root)
    def run(*args):
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=10)
        return result.stdout.strip() if result.returncode == 0 else ""
    name = run("config", "user.name")
    email = run("config", "user.email")
    if name and email:
        return f"{name} <{email}>"
    return name or email or "(unknown)"


def _validate_agent(agent: str):
    if agent not in VALID_AGENTS:
        raise ValueError(f"agent must be one of {VALID_AGENTS}, got {agent!r}")


def render_handoff(*, last_agent: str, operator: str, status: str, task: str, completed: str,
                    changed_files: Optional[Iterable[str]], tests: str, blockers: str,
                    decisions: str, next_action: str, git_snapshot_text: str,
                    ts: Optional[str] = None) -> str:
    _validate_agent(last_agent)
    return (
        f"Last updated: {ts or _now_iso()}\n"
        f"Last agent: {last_agent}\n"
        f"Operator: {operator}\n"
        f"Current status: {status}\n"
        "\n## Task\n"
        f"{task}\n"
        "\n## Completed\n"
        f"{completed}\n"
        "\n## Changed Files\n"
        f"{_bullet_list(changed_files)}\n"
        "\n## Tests\n"
        f"{tests or '(none run)'}\n"
        "\n## Blockers\n"
        f"{blockers or '(none)'}\n"
        "\n## Decisions\n"
        f"{decisions or '(none)'}\n"
        "\n## Next Action\n"
        f"{next_action}\n"
        "\n## Git Snapshot\n"
        f"```text\n{git_snapshot_text}\n```\n"
    )


def write_handoff(repo_root, *, ts: Optional[str] = None, **fields) -> Path:
    path = Path(repo_root) / ".agent" / "HANDOFF.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_handoff(ts=ts, **fields))
    return path


def render_session(*, agent: str, operator: str, ended: str, git_snapshot_text: str, task: str,
                    completed: str, changed_files: Optional[Iterable[str]], tests: str,
                    blockers: str, decisions: str, next_action: str) -> str:
    _validate_agent(agent)
    lines = git_snapshot_text.splitlines()
    branch = next((l.split(": ", 1)[1] for l in lines if l.startswith("Branch: ")), "")
    commit = next((l.split(": ", 1)[1] for l in lines if l.startswith("Recent commit: ")), "")
    return (
        f"- Agent: {agent}\n"
        f"- Operator: {operator}\n"
        f"- Ended: {ended}\n"
        f"- Branch: {branch}\n"
        f"- Recent commit: {commit}\n"
        "\n## Task\n"
        f"{task}\n"
        "\n## Completed\n"
        f"{completed}\n"
        "\n## Changed Files\n"
        f"{_bullet_list(changed_files)}\n"
        "\n## Tests\n"
        f"{tests or '(none run)'}\n"
        "\n## Blockers\n"
        f"{blockers or '(none)'}\n"
        "\n## Decisions\n"
        f"{decisions or '(none)'}\n"
        "\n## Next Action\n"
        f"{next_action}\n"
        "\n## Git Status\n"
        f"```text\n{git_snapshot_text}\n```\n"
    )


def write_session(repo_root, *, agent: str, ts: Optional[str] = None, **fields) -> Path:
    ts = ts or _now_iso()
    sessions_dir = Path(repo_root) / ".agent" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    path = sessions_dir / f"{_stamp_for_filename(ts)}-{agent}.md"
    path.write_text(render_session(agent=agent, ended=ts, **fields))
    return path


def close_session(repo_root, *, agent: str, task: str, completed: str,
                   changed_files: Optional[Iterable[str]] = None, tests: str = "",
                   blockers: str = "", decisions: str = "", next_action: str = "",
                   status: str = "COMPLETED") -> dict:
    """Mirror upstream's `close-session`: write a session file, then rewrite HANDOFF.md from it."""
    _validate_agent(agent)
    changed_files = list(changed_files or [])
    snapshot = git_snapshot(repo_root)
    operator = git_user(repo_root)
    fields = dict(task=task, completed=completed, changed_files=changed_files, tests=tests,
                  blockers=blockers, decisions=decisions, next_action=next_action)
    session_path = write_session(repo_root, agent=agent, operator=operator, git_snapshot_text=snapshot, **fields)
    handoff_path = write_handoff(repo_root, last_agent=agent, operator=operator, status=status,
                                  git_snapshot_text=snapshot, **fields)
    return {"session": str(session_path), "handoff": str(handoff_path)}


def read_handoff(repo_root) -> Optional[str]:
    path = Path(repo_root) / ".agent" / "HANDOFF.md"
    return path.read_text() if path.is_file() else None


def read_latest_session(repo_root) -> Optional[str]:
    sessions_dir = Path(repo_root) / ".agent" / "sessions"
    if not sessions_dir.is_dir():
        return None
    sessions = sorted(sessions_dir.glob("*.md"))
    return sessions[-1].read_text() if sessions else None
