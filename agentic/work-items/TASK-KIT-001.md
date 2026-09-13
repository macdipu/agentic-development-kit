# TASK-KIT-001: Strengthen the kit and add device preview

## Request and scope

User requests: “add some skill for emulator, simulator run for in device preview” and “Specialist skill, Runtime enforcement, Documentation and adoption updates these”. This follows the kit audit's findings about generic skill bodies, unguarded transitions, non-atomic checkpoints, and misleading eval passes.

Classification: technical change, TASK_ONLY, NO_REPLAN. The task is local implementation and validation; it does not authorize deployment or invent human approval records.

## Requirements and evidence

| ID | Acceptance criterion | Implementation / verification |
|---|---|---|
| KIT-01 | Android/iOS previews use explicit targets, launch checks, screenshots, visual inspection, and partial/blocker reporting | [Device skill](../skills/device-preview-agent/SKILL.md), linked command references; skill/link/registry validation |
| KIT-02 | Specialists have distinct procedures, deliverables, and readiness boundaries | [Catalog](../SKILL-CATALOG.md), [handoff contract](../skills/RESULT-CONTRACT.md); structural and skill validation |
| KIT-03 | Unknown/skip transitions, missing evidence/gates, terminal execution, and stale context are denied | [Orchestrator](../runtime/python/agentic_runtime/orchestrator.py), [behavioral tests](../runtime/tests/test_runtime.py) |
| KIT-04 | Run, checkpoint, and audit changes roll back together on persistence failure | [Store](../runtime/python/agentic_runtime/store.py), injected checkpoint failure test |
| KIT-05 | Trusted adapter/tool execution checks pins, capabilities, retries, time/call budgets, cancellation, and idempotency; dry runs suppress declared effects | [Runtime guide](../runtime/README.md), behavioral tests |
| KIT-06 | Evaluations compare real outputs and fail on wrong/empty/unknown cases | [Eval runner](../evals/run_evals.py), eval runner regression tests |
| KIT-07 | Adoption, upgrade, local trust boundary, limitations, and a runnable example are documented | [Adoption](../ADOPTION.md), [demo](../examples/runtime-demo.py), validation script and CI workflow |

## Design boundaries

Use the existing Python standard-library/SQLite runtime. Add coarse ordered routes and a cooperative trusted-adapter API, with transactional local state. Do not introduce a model provider, cloud service, deployment path, automatic human identity, or simulated claims of real device testing. The result contract validates shape and presence of evidence; semantic coverage remains a reviewer/orchestrator responsibility.

## Validation and handoff

Run `sh agentic/scripts/validate-kit.sh` for structure, behavioral tests, evals, and the isolated synthetic demo. Device command references are checked against official Android/Flutter guidance and installed Xcode command help; actual mobile-app execution is outside this kit-only change. Hosted CI has not been run locally.

Task timing is recorded through RuntimeStore in a task-local temporary database. No production release is part of this work item.
