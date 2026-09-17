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
"""
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

VALID_AGENTS = ("claude", "codex")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp_for_filename(ts: str) -> str:
    # 2026-05-13T14:42:35.310000+00:00 -> 2026-05-13T14-42-35-310Z
    dt = datetime.fromisoformat(ts).astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H-%M-%S-") + f"{dt.microsecond // 1000:03d}Z"


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


def _validate_agent(agent: str):
    if agent not in VALID_AGENTS:
        raise ValueError(f"agent must be one of {VALID_AGENTS}, got {agent!r}")


def render_handoff(*, last_agent: str, status: str, goal: str, summary: str,
                    next_step: str, git_snapshot_text: str, notes: str = "", ts: Optional[str] = None) -> str:
    _validate_agent(last_agent)
    return (
        f"Last updated: {ts or _now_iso()}\n"
        f"Last agent: {last_agent}\n"
        f"Current status: {status}\n"
        "\n## Current Goal\n"
        f"{goal}\n"
        "\n## Latest Summary\n"
        f"{summary}\n"
        "\n## Next Step\n"
        f"{next_step}\n"
        "\n## Git Snapshot\n"
        f"```text\n{git_snapshot_text}\n```\n"
        "\n## Notes For Next Agent\n"
        f"{notes}\n"
    )


def write_handoff(repo_root, *, last_agent: str, status: str, goal: str, summary: str,
                   next_step: str, git_snapshot_text: str, notes: str = "", ts: Optional[str] = None) -> Path:
    path = Path(repo_root) / ".agent" / "HANDOFF.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    content = render_handoff(last_agent=last_agent, status=status, goal=goal, summary=summary,
                              next_step=next_step, git_snapshot_text=git_snapshot_text, notes=notes, ts=ts)
    path.write_text(content)
    return path


def write_session(repo_root, *, agent: str, summary: str, git_snapshot_text: str,
                   pickup_guidance: str, ts: Optional[str] = None) -> Path:
    _validate_agent(agent)
    ts = ts or _now_iso()
    sessions_dir = Path(repo_root) / ".agent" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    path = sessions_dir / f"{_stamp_for_filename(ts)}-{agent}.md"
    lines = git_snapshot_text.splitlines()
    branch = next((l.split(": ", 1)[1] for l in lines if l.startswith("Branch: ")), "")
    commit = next((l.split(": ", 1)[1] for l in lines if l.startswith("Recent commit: ")), "")
    content = (
        f"- Agent: {agent}\n"
        f"- Ended: {ts}\n"
        f"- Branch: {branch}\n"
        f"- Recent commit: {commit}\n"
        "\n## Summary\n"
        f"{summary}\n"
        "\n## Git Status\n"
        f"```text\n{git_snapshot_text}\n```\n"
        "\n## Pickup Guidance\n"
        f"{pickup_guidance}\n"
    )
    path.write_text(content)
    return path


def close_session(repo_root, *, agent: str, summary: str, status: str = "COMPLETED",
                   goal: str = "", next_step: str = "", notes: str = "",
                   pickup_guidance: str = "") -> dict:
    """Mirror upstream's `close-session`: write a session file, then rewrite HANDOFF.md from it."""
    _validate_agent(agent)
    snapshot = git_snapshot(repo_root)
    session_path = write_session(repo_root, agent=agent, summary=summary,
                                  git_snapshot_text=snapshot, pickup_guidance=pickup_guidance or summary)
    handoff_path = write_handoff(repo_root, last_agent=agent, status=status, goal=goal,
                                  summary=summary, next_step=next_step,
                                  git_snapshot_text=snapshot, notes=notes)
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
