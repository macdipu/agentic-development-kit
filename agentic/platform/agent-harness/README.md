# Agent Harness

`Orchestrator.execute` checks stage eligibility, instruction pins, context, gates, attempt budgets, results, and timing. Registered tool calls pass through its capability/idempotency gateway. Adapters are trusted Python callbacks; process isolation and hard interruption require a worker supervisor.

See the [runtime capability matrix](../../runtime/README.md#capability-matrix) and [production checklist](../agent-harness/production-readiness.md).
