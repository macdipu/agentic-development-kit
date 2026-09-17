# Agentic Development Kit

This directory contains the reusable agentic development system for the host project.

## Layout

Two kinds of thing live under `agentic/`: the reusable **kit** (code, skills, templates — same in every project, changes only when the kit itself is upgraded) and **data** (per-project state, logs, and generated docs — grows as the project runs). They stay in separate top-level folders so it's obvious which is which.

```text
agentic/
├── README.md, MANIFEST.md, SKILL-CATALOG.md, ADOPTION.md   # kit docs
├── kit/                          # reusable source
│   ├── skills/                   # specialist definitions
│   ├── workflows/                # routing per work type
│   ├── templates/                # blank artifacts and production evidence template
│   ├── policies/                 # default policy
│   ├── config/                   # permissions, commands, skills, hooks
│   ├── examples/                 # isolated smoke and legacy delivery fixtures
│   ├── scripts/                  # installer and validation
│   └── runtime/                  # runtime guides, hooks, Python package, tests
└── data/                              # DATA — see data/README.md
    ├── project-context/                # per-project discovery cache + generated feature docs
    ├── work-items/                       # freeform task docs (not templated feature artifacts)
    └── runtime/
        ├── state/                          # gitignored — active-task pointer, run DB
        └── logs/                             # gitignored
```

Never put generated or per-project content in the kit folders above `data/`; never put skill/template/config source in `data/`. See `agentic/data/README.md` for what goes in each data subfolder.

## Usage

Start with the [adoption guide](ADOPTION.md) for installation and upgrades, and the [runtime guide](kit/runtime/README.md) for executable commands and capability limits. All specialists use the shared [handoff contract](kit/skills/RESULT-CONTRACT.md).

Keep `AGENTS.md` and `CLAUDE.md` at the repository root. The host project's existing root `README.md` remains the project README.

The kit supports both prompt-first and document-first intake. Both are normalized into the same canonical work-item flow. Derived artifacts (SRS, architecture, tech spec, ADRs, tasks) are stored per work item under `agentic/data/project-context/features/<work-item-id>/` — see that folder's `README.md` for the layout and `agentic/kit/templates/` for each artifact's template.

```text
Prompt ------------------+
                         |
                         v
                 Canonical Work Item
                         ^
                         |
FEATURE.md / CR.md -------+
```

The workflow directs agents to load context first, identify affected modules, and refresh only stale or missing slices. In local harness mode, callers register scoped files; the runtime checks their fingerprints and eligible stages. Automatic scope discovery and model execution require adapters.

---

# Full Agentic SDLC Workflow

## Business and Technical Preparation

```text
CLIENT / BUSINESS INPUT
        |
        v
+------------------------------+
| 1. BRD                       |
| Business Requirement Doc     |
| + Mock UI                    |
| + Wireframe                  |
+--------------+---------------+
               |
               v
+------------------------------+
| 2. SRS + UI                  |
| Software Requirement Spec    |
| + Final / Prepared UI        |
|                              |
| Status: READY                |
+--------------+---------------+
               |
               v
+------------------------------+
| 3. TECHNICAL PREPARATION     |
|                              |
| - Requirement List           |
| - ADR when required          |
| - Technical Specification    |
| - LLD / Coding Convention    |
| - Client-facing docs         |
| - System Design              |
| - Technical Review           |
+--------------+---------------+
               |
               v
        TECHNICAL READY
```

## Planning, Sprint, Implementation, and QA

```text
Technical Ready
      |
      v
Work Item Level Classifier
      |
      +--> Epic -> Stories -> Tasks
      +--> Stories -> Tasks
      +--> Tasks only
      +--> Existing Task -> Execute
      |
      v
Sprint Handling Decision
      |
      +--> Full Sprint Planning
      +--> Add to Existing Sprint
      +--> Backlog Only
      +--> Expedited
      +--> No Replan
      |
      v
+-------------------------------+
| TL / LEAD / PLANNING          |
|                               |
| - Pick affected module(s)     |
| - Create/select Epic if needed|
| - Define Stories if needed    |
| - Identify dependencies       |
| - Sequence/parallelize work   |
| - Assign work / agent lanes   |
| - Consider capacity           |
| - Set UAT target if relevant  |
+---------------+---------------+
                |
                v
+-------------------------------+
| VERIFIER / QA                 |
|                               |
| Verify planned scope          |
| Check:                        |
| - Frontend / Mobile           |
| - Backend                     |
| - Database / Integration      |
| - Testing / QA                |
| - Security / DevOps           |
| - Development dependencies    |
+---------------+---------------+
                |
                v
+-------------------------------+
| TASK BREAKDOWN                |
|                               |
| - FE / Mobile Tasks           |
| - BE Tasks                    |
| - DB / Integration Tasks      |
| - QA Tasks                    |
| - Security / DevOps Tasks     |
+---------------+---------------+
                |
                v
          IMPLEMENTATION
                |
                v
            CODE REVIEW
                |
                v
+-------------------------------+
| AUTO QA                       |
| Agent / pipeline checks       |
+---------------+---------------+
                |
                v
+-------------------------------+
| MANUAL QA                     |
| Human verification            |
+---------------+---------------+
                |
        PASS ---+--- FAIL
         |             |
         v             +------> Rework / Tasks
        UAT
         |
         v
  RELEASE READINESS
         |
         v
       RELEASE
```

## Agent View

```text
Human / Client
      |
      v
Requirement Agent
      |
      v
Architecture Agent
      |
      v
Technical Readiness
      |
      v
Work-Level Classifier
      |
      v
Sprint Planning Agent (only when needed)
      |
      v
Epic / Story Verification
      |
      v
Task Breakdown Agent
      |
      v
Development Agents
   /      |       \
 FE      BE      Test/QA
   \      |       /
      Code Review
          |
          v
     Review Agent
          |
          v
      Auto QA Agent
          |
          v
       Manual QA
          |
          v
       UAT / Release
```

---

# Work Hierarchy: Feature, Epic, Story, and Task

These are different planning levels. Do not create all levels mechanically.

```text
Feature
  |
  v
Epic
  |
  v
Story
  |
  v
Task
```

## Feature

A **Feature** is a business capability or product-level outcome the organization wants to introduce or change.

Examples: Gift Transfer, Scheduled Bank Transfer, Card Replacement, Beneficiary Management.

A Feature answers:
- What capability are we delivering?
- Why is it needed?
- What is in scope and out of scope?

The canonical feature artifact is normally `FEATURE.md`.

## Epic

An **Epic** is a large delivery scope that groups related Stories needed to deliver a significant portion of a Feature.

Example:

```text
Feature: Gift Transfer
Epic: Gift Transfer User Flow
```

An Epic may group Stories such as Select Recipient, Enter Amount, Review Charges, Authorize Transfer, and Show Result.

An Epic is normally too large to implement as one independently testable unit.

## Story

A **Story** is a smaller, independently understandable user or business outcome inside a Feature or Epic. It should have coherent acceptance criteria.

Example:

```text
Story: Select Gift Recipient
```

A Story answers:
- What specific outcome must work?
- How will we know it is complete?

## Task

A **Task** is a concrete engineering unit of work required to implement or verify a Story or small work item.

Example:

```text
Story: Select Gift Recipient
Tasks:
- FE-101: Add recipient selection screen
- FE-102: Reuse beneficiary component
- BE-101: Extend beneficiary lookup integration if needed
- QA-101: Add recipient validation tests
```

Tasks may be Frontend, Backend, Mobile, Database, Integration, QA, Security, DevOps, or Documentation.

## Minimum useful hierarchy

```text
Large / multi-flow capability
  -> Feature -> Epic -> Stories -> Tasks

Normal bounded capability
  -> Feature -> Stories -> Tasks

Small localized Feature / CR / technical change
  -> Work Item -> Tasks

Existing approved and planned task
  -> Execute Existing Task
```

Do not force `Feature -> Epic -> Story -> Task` when it adds administration without improving delivery clarity.

---

# When Sprint Planning Runs

Sprint Planning is **conditional for every work type**, including Features and CRs. The request type alone does not decide it.

Use these possible outcomes:

```text
FULL_SPRINT_PLANNING
ADD_TO_EXISTING_SPRINT
BACKLOG_ONLY
EXPEDITED
NO_REPLAN
```

Examples:

| Work shape | Hierarchy | Sprint handling |
|---|---|---|
| Tiny bounded change | Task | No full planning / add to sprint or backlog |
| Small feature | Story -> Tasks or Tasks | Add to existing sprint/backlog |
| Medium feature | Stories -> Tasks | Sprint Planning |
| Large feature | Epic -> Stories -> Tasks | Full Sprint Planning |
| Small CR | Task(s) | No replan / add to sprint |
| Medium CR | Story -> Tasks | Sprint Planning |
| Large CR | Epic/Stories -> Tasks | Full Sprint Planning |
| Existing approved task | Task | Execute directly / no replan |
| Emergency hotfix | Task(s) | Expedited planning |

Sprint Planning is useful when work needs meaningful sequencing, multiple teams/modules, coordinated dependencies, capacity decisions, or a UAT target. It should not be forced for every request.

---

# Context-First Legacy Development

For existing projects, do not audit the whole repository on every task.

```text
Incoming Work
     |
     v
Load Project Context
     |
Context usable?
   /       \
 YES       NO
  |         |
  |         v
  |    Bootstrap required scope
  |         |
  +---------+
       |
       v
Identify affected modules/features
       |
       v
Load module/feature context
       |
Context sufficient?
   /       \
 YES       NO
  |         |
  |         v
  |    Incremental discovery
  |         |
  +---------+
       |
       v
Continue feature / CR / bug / hotfix workflow
```

Persist evidence-backed context so future work can reuse it.

---

# Skill Routing

The Workflow Orchestrator is the final authority for selecting skills. It uses:

```text
Work Type
+ Workflow Stage
+ Project / Module Context
+ Work-Level Classification
+ Change Impact
+ Sprint Handling Decision
+ Policy
+ Approval State
```

Individual skills must not autonomously bypass the orchestrator or required human gates.

---

# Documentation and ADR Rules

Update documentation based on impact. Do not rewrite every document after every change.

Create an ADR only when the work introduces or changes a significant architectural decision, such as a new service boundary, integration architecture, authentication strategy, messaging pattern, database technology, or major breaking architectural change.

Normal UI changes, local validation changes, or endpoints following an established pattern generally do not require a new ADR.

---

# Human Approval

Artifact creation is not approval.

```text
Artifact Created != Artifact Approved
```

Typical gates include Requirements, Architecture, Sprint/Epic planning when policy requires it, Code Review, QA, UAT, and Release.

---

# Agent Task Timing

The platform timing target includes the fields below. The local runtime currently records start/end/failure events, durations for completed or failed adapters, and retry counts; queue and wait-time attribution require a worker/observability adapter:

```text
queued_at
started_at
ended_at
duration_ms
queue_wait_ms
active_execution_ms
tool_wait_ms
approval_wait_ms
retry_count
```

Timing may be aggregated by Task, Feature/CR, Workflow, Agent, Skill, or Project.

---

# Production Harness Runtime

The kit includes a small provider-neutral reference runtime under `agentic/kit/runtime/`. It turns core governance concepts into executable behavior instead of leaving them only as documentation.

It includes atomic workflow/checkpoint/audit persistence, explicit scope-bound approvals, ordered transitions, context hash checks, pinned skill eligibility, validated handoffs, bounded adapter attempts, and a tool gateway with capability checks and dry-run suppression. Read the [capability matrix](kit/runtime/README.md#capability-matrix) before relying on a control.

```text
Developer Prompt / Work Document
        ↓
Canonical Work Item
        ↓
Context Engine
        ↓
Workflow Orchestrator
        ↓
Policy + Approval Checks
        ↓
Agent Harness
        ↓
Skill + Approved Tools + Model Adapter
        ↓
Checkpoint + Timing + Audit + Artifacts
```

The supplied runtime is a local reference implementation for trusted adapters. Replacing the local JSON-file store alone does not create production isolation, authenticated approvals, or hard cancellation. Those boundaries need organization-specific infrastructure; production actions are unsupported by this runtime.
