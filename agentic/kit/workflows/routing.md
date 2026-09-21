# Routing

```text
Incoming Request
  -> Determine input mode
  -> Normalize to canonical work item
  -> Load project context
  -> Determine project type
  -> Classify work type
  -> Resolve affected modules/features
  -> Evaluate policy and approvals
  -> Select next skill
```

The orchestrator, not an individual specialist skill, selects the next workflow step.

## Mobile device preview

For requests to run or preview an existing mobile app in an emulator, simulator, or a requested connected device, select `device-preview-agent` after loading relevant app context. Treat a standalone preview as `TASK_ONLY` with `NO_REPLAN`; do not require new feature or sprint artifacts for running existing work.

During implementation or QA, select the same skill when mobile changes need on-device visual evidence. Return its screenshots, observed checks, and blockers to the calling workflow. A successful preview does not replace automated tests or human approval gates. Route code fixes beyond the preview scope back through implementation.

## Web preview

For requests to run or preview an existing web app in a browser via a local dev server, select `web-preview-agent` after loading relevant app context. Treat a standalone preview as `TASK_ONLY` with `NO_REPLAN`; do not require new feature or sprint artifacts for running existing work.

During implementation or QA, select the same skill when web changes need browser-based visual evidence. Return its screenshots, observed checks, and blockers to the calling workflow. A successful preview does not replace automated tests or human approval gates. Route code fixes beyond the preview scope back through implementation.

## Domain agent selection

Once `task-breakdown-agent` sets a task's `Category` (`agentic/kit/templates/task.md`), the matching persona in `agentic/kit/agents/` picks it up: `fe-agent`, `mobile-agent`, `be-agent`, `db-integration-agent`, `qa-agent`, or `security-devops-agent` (see `agentic/kit/agents/README.md`). `fe-agent` and `mobile-agent` are split deliberately -- they preview through different skills (`web-preview-agent` vs `device-preview-agent`). This changes nothing about orchestrator mechanics -- eligibility and pins stay keyed by skill name; the persona only narrows which tasks a given execution stays scoped to and which of its composed skills it runs (still selected explicitly via `task-start --skill <name>`, same as any other skill).

`Documentation`-categorized tasks have no matching persona -- route them directly to `implementation-agent`.
