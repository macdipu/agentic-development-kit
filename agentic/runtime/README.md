# Reference Harness Runtime

This directory contains a provider-neutral reference runtime that turns the kit's workflow rules into enforceable behavior. It is intentionally small and uses Python's standard library so teams can replace individual components with production infrastructure later.

Implemented reference capabilities:

- durable workflow state in SQLite
- checkpoints and resume metadata
- explicit approval records
- context freshness using Git revisions and file hashes
- module dependency graph
- skill registry and workflow eligibility
- tool registry and capability checks
- deterministic policy evaluation
- task timing and run lineage
- bounded retry metadata and cancellation state
- dry-run mode
- basic secret redaction before model/tool context

The runtime does not embed a model provider, Jira SDK, Git hosting SDK, CI/CD SDK, or production database. Those integrations belong behind adapters in `agentic/platform/`.

## Quick start

```bash
python3 agentic/runtime/python/agentic_runtime/cli.py init
python3 agentic/runtime/python/agentic_runtime/cli.py start --project internet-banking --type new_feature --title "Gift Transfer"
python3 agentic/runtime/python/agentic_runtime/cli.py list
```

State is written under `agentic/runtime/state/` and should normally remain local until the team chooses a shared persistence backend.
