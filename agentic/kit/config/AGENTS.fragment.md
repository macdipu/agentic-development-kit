# Agentic kit workflow

Use `agentic/README.md` and `agentic/kit/workflows/routing.md` for lifecycle routing.
Load relevant `agentic/data/project-context/` before discovering affected code.
Reuse existing patterns and refresh only stale context needed for the request.
Classify the minimum useful work hierarchy; sprint planning is conditional.
Preserve traceability from the request through requirements, implementation, QA,
and release evidence. Generated artifacts and host work items belong under
`agentic/data/`; reusable skills, templates, and runtime belong under `agentic/kit/`.
Never infer missing business rules or human approval.

Instruction mode guides agent behavior. In local-harness mode, use the runtime
task protocol and verify installation with its `doctor` command. Before starting
new work, run `python3 agentic/kit/runtime/hooks/session_start_check.py` when the
agent platform has no SessionStart hook. Resume midflight work before starting
another run. Unknown or damaged state requires explicit recovery.

Record execution timing through the harness. Before compaction, checkpoint
active work and update affected task/context documents with remaining work.

Read `.agent/HANDOFF.md` and the latest `.agent/sessions/*.md` entry before
starting work (or run `agentic_runtime.cli pickup`) -- cross-agent-platform
handoff notes any agent, on any platform, can read after `git pull`. When
finishing a work session, run `agentic_runtime.cli close-session --agent
<claude|codex> --status <RUNNING|BLOCKED|COMPLETED|CANCELLED> --task "..."
--completed "..." --next-action "..."` (automatic
via the `Stop` hook where supported) so the next agent, on this platform or
another, can continue from git alone.
