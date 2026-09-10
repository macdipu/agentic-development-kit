---
name: document-intake-adapter
description: Load and validate an existing FEATURE.md, CR.md, BUG.md, HOTFIX.md, or equivalent work-item document and normalize it for the Agentic SDLC.
---

# Document Intake Adapter

## Operating rules

1. Load only the relevant work item and project/module context required for this responsibility.
2. Reuse fresh context; request incremental discovery only when required.
3. Never invent missing business rules.
4. Never infer human approval.
5. Preserve evidence and traceability.
6. Stay inside this skill's responsibility.
7. Return explicit status, blockers, open questions, and recommended next step.
8. Return results to the Workflow Orchestrator for routing.
9. Do not perform production-impacting actions unless policy and explicit approval permit them.
10. Do not report guessed task timing; timing is measured by the harness.
