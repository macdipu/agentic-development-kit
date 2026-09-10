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
