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
