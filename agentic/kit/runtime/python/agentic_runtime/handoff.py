"""Cross-agent-platform handoff files, compatible with github.com/ishipu/agent-handoff.

Python-native reimplementation of that project's file format (it is a small,
zero-runtime-dependency Node/TS CLI; rather than add a Node toolchain to this
Python-only kit, its ~5 template functions are ported here directly). Like
RuntimeStore's ledger beside them in `.agent/runtime/`, these files are
meant to be committed: `.agent/HANDOFF.md` + `.agent/sessions/*.md` are the
plain-text handoff notes any agent platform (Claude Code, Codex, ...) reads
on pickup and writes on close, so a different tool on a different machine can
continue the same work from what's in git -- no server.

Upstream restricts `agent` to exactly "claude" or "codex"; this module keeps
that restriction so files stay valid input to the real agent-handoff CLI too.

Handoff content is structured (task/completed/changed_files/tests/blockers/
decisions/next_action) rather than one free-form summary string, so a picking-up
agent -- or a script -- can read a specific field instead of parsing prose, and
so a closing agent can't skip a category by writing one vague sentence. The
Commits section is derived from git, not supplied by the caller: every commit
since the previous session record's HEAD, tagged with its Commit-Trigger /
Work-Item / Task trailers (see commits.py). The Runtime section is likewise
derived, not supplied: the governed run's full ledger (see summarize_run), so
the committed record carries the run's state, not just its id.
"""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from agentic_runtime import commits as commit_log
from agentic_runtime.timing import durations

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


def _fmt_ms(ms) -> str:
    if ms is None:
        return "running"
    seconds = int(ms // 1000)
    return f"{seconds // 60}m{seconds % 60:02d}s" if seconds >= 60 else f"{seconds}s"


def _compact(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _section(title: str, rows: list) -> list:
    return [f"\n### {title}", *rows] if rows else [f"\n### {title}", "(none)"]


def summarize_run(store, run_id: str) -> str:
    """Full markdown rendering of one run's ledger, for the committed Runtime section.

    Every approval, timing span, attempt, checkpoint, audit event (payloads are
    already redacted at write time) and tool call. Checkpoint payloads are left
    out: each is a copy of the run metadata already rendered above them.
    """
    run = store.get_run(run_id)
    if run is None:
        return f"Run {run_id} not found in store."
    data = store.ledger(run_id)
    meta = run.metadata
    task = meta.get("active_task")
    lines = [
        f"- Run: {run.run_id}",
        f"- Project: {run.project} | Work type: {run.work_type} | Planning: {meta.get('planning', '')}",
        f"- Title: {run.title}",
        f"- Stage: {run.stage} | Status: {run.status} | Dry run: {run.dry_run}",
        f"- Scope revision: {meta.get('scope_revision', 0)} | Runtime version: {meta.get('runtime_version', '')}",
        f"- Created: {run.created_at} | Updated: {run.updated_at}",
        f"- Config hash: {meta.get('config_hash', '')}",
        f"- Active task: {_compact(task)}" if task else "- Active task: (none)",
    ]
    results = meta.get("results", {})
    route = meta.get("route") or list(results)
    stage_rows = []
    for stage in route:
        result = results.get(stage)
        if not result:
            stage_rows.append(f"- {stage}: PENDING")
            continue
        stage_rows.append(f"- {stage}: {result.get('status')}")
        for key in ("evidence", "blocking_issues", "open_questions"):
            if result.get(key):
                stage_rows.append(f"  - {key}: {', '.join(map(str, result[key]))}")
        if result.get("recommended_next_step"):
            stage_rows.append(f"  - next: {result['recommended_next_step']}")
        if result.get("outputs"):
            stage_rows.append(f"  - outputs: {_compact(result['outputs'])}")
    lines += _section("Stages", stage_rows)
    lines += _section("Approvals", [
        f"- {a['created_at']} {a['gate']}: {a['decision']} by {a['approver']} (rev {a['scope_revision']})"
        + (f" -- {a['comment']}" if a.get("comment") else "")
        for a in data.get("approvals", [])])
    skills = {e["task"]: e["metadata"].get("skill") for e in data.get("timing_events", [])
              if e["event"] == "STARTED" and e.get("metadata", {}).get("skill")}
    spans = durations(data.get("timing_events", []))
    total = sum(s["duration_ms"] or 0 for s in spans)
    lines += _section(f"Timing (total {_fmt_ms(total)})", [
        f"- {s['started_at']} {skills.get(s['task'], s['task'])}: {s['event']} {_fmt_ms(s['duration_ms'])} (task {s['task']})"
        for s in spans])
    lines += _section("Attempts", [f"- {key}: {count}" for key, count in sorted(meta.get("attempts", {}).items())])
    lines += _section("Budget Overrides", [f"- {key}: {value}" for key, value in sorted(meta.get("budget_overrides", {}).items())])
    lines += _section("Context Files", [f"- {path}: {digest}" for path, digest in sorted(meta.get("context", {}).get("files", {}).items())])
    pins = sorted(meta.get("skill_pins", {}).items())
    lines += [f"\n### Skill Pins ({len(pins)})", "<details><summary>skill revisions</summary>\n",
              *(f"- {skill}: {rev}" for skill, rev in pins), "\n</details>"] if pins else _section("Skill Pins", [])
    lines += _section("Checkpoints", [f"- {c['created_at']} {c['stage']} {c['status']}" for c in data.get("checkpoints", [])])
    lines += _section("Audit", [
        f"- {e['created_at']} {e['event']}" + (f" {_compact(e['payload'])}" if e.get("payload") else "")
        for e in data.get("audit_events", [])])
    lines += _section("Tool Calls", [f"- {key}: {call.get('status')}" for key, call in sorted(data.get("tool_calls", {}).items())])
    return "\n".join(lines)


def _validate_agent(agent: str):
    if agent not in VALID_AGENTS:
        raise ValueError(f"agent must be one of {VALID_AGENTS}, got {agent!r}")


def render_handoff(*, last_agent: str, operator: str, status: str, task: str, completed: str,
                    changed_files: Optional[Iterable[str]], tests: str, blockers: str,
                    decisions: str, next_action: str, git_snapshot_text: str,
                    commits: Optional[Iterable[str]] = None, runtime: str = "",
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
        "\n## Runtime\n"
        f"{runtime or '(no governed run)'}\n"
        "\n## Commits\n"
        f"{_bullet_list(commits)}\n"
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
                    blockers: str, decisions: str, next_action: str,
                    commits: Optional[Iterable[str]] = None, runtime: str = "",
                    session_id: Optional[str] = None) -> str:
    _validate_agent(agent)
    lines = git_snapshot_text.splitlines()
    branch = next((l.split(": ", 1)[1] for l in lines if l.startswith("Branch: ")), "")
    commit = next((l.split(": ", 1)[1] for l in lines if l.startswith("Recent commit: ")), "")
    return (
        f"- Agent: {agent}\n"
        f"- Operator: {operator}\n"
        f"- Ended: {ended}\n"
        + (f"- Session: {session_id}\n" if session_id else "")
        + f"- Branch: {branch}\n"
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
        "\n## Runtime\n"
        f"{runtime or '(no governed run)'}\n"
        "\n## Commits\n"
        f"{_bullet_list(commits)}\n"
        "\n## Git Status\n"
        f"```text\n{git_snapshot_text}\n```\n"
    )


def _session_file(repo_root, session_id: Optional[str]) -> Optional[Path]:
    """The record an earlier close in the same agent session wrote, if any."""
    sessions_dir = Path(repo_root) / ".agent" / "sessions"
    if not session_id or not sessions_dir.is_dir():
        return None
    marker = f"- Session: {session_id}\n"
    return next((p for p in sorted(sessions_dir.glob("*.md"), reverse=True) if marker in p.read_text()), None)


def write_session(repo_root, *, agent: str, ts: Optional[str] = None, session_id: Optional[str] = None,
                  **fields) -> Path:
    """New record per close, or -- given a session_id -- one record per agent session,
    rewritten in place on each close (a Stop hook fires after every reply)."""
    ts = ts or _now_iso()
    sessions_dir = Path(repo_root) / ".agent" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    path = _session_file(repo_root, session_id) or sessions_dir / f"{_stamp_for_filename(ts)}-{agent}.md"
    path.write_text(render_session(agent=agent, ended=ts, session_id=session_id, **fields))
    return path


def close_session(repo_root, *, agent: str, task: str, completed: str, status: str,
                   changed_files: Optional[Iterable[str]] = None, tests: str = "",
                   blockers: str = "", decisions: str = "", next_action: str = "",
                   store=None, run_id: Optional[str] = None, session_id: Optional[str] = None) -> dict:
    """Mirror upstream's `close-session`: write a session file, then rewrite HANDOFF.md from it."""
    _validate_agent(agent)
    changed_files = list(changed_files or [])
    snapshot = git_snapshot(repo_root)
    operator = git_user(repo_root)
    base = previous_session_head(repo_root, exclude=_session_file(repo_root, session_id))
    commits = commit_log.format_commit_lines(commit_log.commits_since(repo_root, base))
    fields = dict(task=task, completed=completed, changed_files=changed_files, tests=tests,
                  blockers=blockers, decisions=decisions, next_action=next_action, commits=commits,
                  runtime=summarize_run(store, run_id) if store is not None and run_id else "")
    session_path = write_session(repo_root, agent=agent, operator=operator, git_snapshot_text=snapshot,
                                 session_id=session_id, **fields)
    handoff_path = write_handoff(repo_root, last_agent=agent, operator=operator, status=status,
                                  git_snapshot_text=snapshot, **fields)
    return {"session": str(session_path), "handoff": str(handoff_path)}


def previous_session_head(repo_root, exclude: Optional[Path] = None) -> Optional[str]:
    """The commit the latest session record ended on -- the base for this session's commit log.
    `exclude` skips the current session's own record when it is being rewritten."""
    latest = read_latest_session(repo_root, exclude=exclude) or ''
    line = next((l for l in latest.splitlines() if l.startswith('- Recent commit: ')), '')
    sha = line.split(': ', 1)[1].split(' ', 1)[0] if line else ''
    return sha if sha and sha != '(unavailable)' else None


def read_handoff(repo_root) -> Optional[str]:
    path = Path(repo_root) / ".agent" / "HANDOFF.md"
    return path.read_text() if path.is_file() else None


def read_latest_session(repo_root, exclude: Optional[Path] = None) -> Optional[str]:
    sessions_dir = Path(repo_root) / ".agent" / "sessions"
    if not sessions_dir.is_dir():
        return None
    sessions = [p for p in sorted(sessions_dir.glob("*.md")) if p != exclude]
    return sessions[-1].read_text() if sessions else None
