# Skill Catalog

## Tiers

Not every skill runs on every work item. The **core** tier is the minimum path a
governed run takes; **on-demand** skills run only when classification, impact, or
missing context calls for them. Skipping an on-demand skill is correct, not a gap.

| Tier | Skills | When |
|---|---|---|
| Core | `prompt-intake-adapter` or `document-intake-adapter`; `baseline-verifier`; `business-requirement-analyzer` (feature) or `change-impact-analyzer` (CR/bug/hotfix); `technical-readiness-verifier`; `work-item-level-classifier`; `implementation-agent`; `code-review-agent`; `automated-qa-agent`; `release-readiness-agent` | Every governed run. The classifier's `TASK_ONLY` verdict plus the verifier's `TECHNICAL_READY` verdict (each recorded by that skill) are what `approve --auto` checks. |
| Discovery (on-demand) | `project-discovery-agent`, `architecture-reverse-engineer`, `api-contract-discovery-agent`, `database-discovery-agent`, `user-flow-discovery-agent`, `runtime-discovery-agent`, `history-analysis-agent`, `requirement-reconstruction-agent`, `test-baseline-agent`, `brownfield-risk-analyzer` | Only for the module/feature whose context is `MISSING` or `STALE` (`cli.py context-check`). |
| Design (on-demand) | `srs-generator`, `requirement-ui-verifier`, `technical-architecture-planner`, `technical-spec-generator`, `adr-generator` | When requirements, a screen, or an architectural decision is actually new. |
| Planning (triggered) | `sprint-planner`, `sprint-readiness-verifier`, `epic-verifier`, `task-breakdown-agent`, `effort-estimation-agent` | Whenever the classifier's verdict adds a PLANNING stage (`STORY_TASK`/`EPIC_STORY_TASK`, or sprint/backlog handling); the runtime then requires the Epic/Story/Task/sprint files before implementation. |
| Preview (on-demand) | `device-preview-agent`, `web-preview-agent` | When visual evidence is needed. |
| Routing | `agentic-sdlc-orchestrator`, `intake-change-classifier` | Coordinates the above; usually not a separate task. |

## Skills

- `adr-generator` - Create ADRs only for significant architecture decisions, including alternatives, consequences, risks, and status.
- `agentic-sdlc-orchestrator` - Coordinate Agentic SDLC workflows for greenfield and brownfield projects. Use to normalize work, load context, classify work and planning level, decide whether sprint planning is required, select specialist skills, enforce workflow state and approvals, and route Features, CRs, bugs, hotfixes, technical changes, and existing tasks through the minimum necessary lifecycle.
- `api-contract-discovery-agent` - Recover existing API routes, contracts, auth, validation, consumers, and implementations from code, specs, clients, tests, and runtime evidence.
- `architecture-reverse-engineer` - Recover evidence-backed current architecture from legacy code and artifacts, distinguishing confirmed, inferred, and unknown findings.
- `automated-qa-agent` - Evaluate build, lint, static analysis, unit, integration, contract, security, regression, and acceptance evidence.
- `baseline-verifier` - Verify a recovered brownfield baseline against available evidence and human corrections before marking context usable.
- `brownfield-risk-analyzer` - Assess legacy areas for coupling, missing tests, unknown ownership, hard-coded rules, unsupported dependencies, security, and operational risk.
- `business-requirement-analyzer` - Extract functional and non-functional requirements, business rules, actors, constraints, acceptance criteria, conflicts, and open questions.
- `change-impact-analyzer` - Analyze a change request against the current baseline and identify affected requirements, modules, UI, APIs, database, architecture, code, tests, security, approvals, and workflow gates.
- `code-review-agent` - Review implementation against requirements, architecture, security, reliability, conventions, tests, and unintended changes.
- `database-discovery-agent` - Recover database schemas, relationships, ownership, migrations, indexes, transaction boundaries, and risks.
- `device-preview-agent` - Build, launch, and visually verify mobile apps in Android emulators, iOS simulators, or a requested connected device, with screenshots and targeted UI smoke checks.
- `web-preview-agent` - Build, launch, and visually verify web apps in a browser via a local dev server, with screenshots and targeted UI smoke checks.
- `document-intake-adapter` - Load and validate an existing FEATURE.md, CR.md, BUG.md, HOTFIX.md, or equivalent work-item document and normalize it for the Agentic SDLC.
- `effort-estimation-agent` - Assess relative implementation effort, uncertainty, dependency sequencing, critical path, and parallelizable work for software features, change requests, bugs, hotfixes, and technical changes. Use when planning needs delivery sizing or sequencing; do not invent precise calendar estimates when evidence is insufficient.
- `epic-verifier` - Verify that an epic fully covers approved scope, acceptance criteria, UI, technical impacts, QA, security, and dependencies.
- `history-analysis-agent` - Analyze Git, PR, issue, release, and incident history to recover legacy rationale and constraints.
- `implementation-agent` - Implement an approved task using project context, existing architecture, reusable patterns, tests, and strict scope control.
- `intake-change-classifier` - Classify incoming software work as new feature, change request, bug, hotfix, technical change, security/regulatory change, or discovery work.
- `project-discovery-agent` - Discover repository structure, modules, frameworks, dependencies, build systems, tests, CI/CD, and unknown areas when context is missing.
- `prompt-intake-adapter` - Convert a developer prompt describing a feature, CR, bug, hotfix, or technical change into a canonical work item without inventing missing requirements.
- `release-readiness-agent` - Assess code review, QA, UAT, migration, rollback, configuration, monitoring, and approval evidence before release.
- `requirement-reconstruction-agent` - Reconstruct evidence-backed as-is behavior from code, UI, APIs, DB, tests, and history without presenting inference as business truth.
- `requirement-ui-verifier` - Verify consistency among requirements, SRS, UI, validation, permissions, errors, and acceptance criteria.
- `runtime-discovery-agent` - Recover runtime/deployment topology from permitted infrastructure, configuration, manifests, logs, and operational evidence.
- `sprint-planner` - Plan sprint delivery for software work when planning is actually required, regardless of whether the work is a Feature, CR, bug, hotfix, or technical change. Use after work-level classification when the orchestrator selects FULL_SPRINT_PLANNING or ADD_TO_EXISTING_SPRINT and delivery sequencing, dependencies, ownership, capacity, or UAT targeting must be coordinated.
- `sprint-readiness-verifier` - Verify whether software work is ready to be committed to a sprint or should remain in backlog, be expedited, or require more preparation. Use for features, change requests, bugs, hotfixes, and technical changes after technical readiness and planning-level classification when sprint commitment is being considered.
- `srs-generator` - Create a traceable software requirements specification from approved requirements and constraints.
- `task-breakdown-agent` - Break verified work into implementation-ready FE, BE, DB, integration, QA, DevOps, security, and documentation tasks.
- `technical-architecture-planner` - Design or update architecture (HLD) from verified requirements and current project context while preferring existing project patterns.
- `technical-readiness-verifier` - Determine whether work is technically ready, conditionally ready, or blocked.
- `technical-spec-generator` - Produce implementation-ready technical specification (LLD), API contracts, database impact, security, error handling, observability, dependencies, and test strategy.
- `test-baseline-agent` - Map current behavior/modules to test evidence and identify coverage gaps, flaky/broken tests, and regression risk.
- `user-flow-discovery-agent` - Recover screens, navigation, forms, validations, state transitions, permissions, and user flows from frontend/mobile evidence.
- `work-item-level-classifier` - Classify incoming or analyzed software work into the minimum useful planning hierarchy: EPIC_STORY_TASK, STORY_TASK, TASK_ONLY, or EXECUTE_EXISTING_TASK. Use after requirements or change impact are understood and before sprint handling or task decomposition, for features, change requests, bugs, hotfixes, and technical changes.
