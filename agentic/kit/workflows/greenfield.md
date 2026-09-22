# Greenfield

```text
BRD / PRD / Prompt / Feature Doc
 -> Check agentic/data/project-context/{BRD,PRD,SRD,ARCHITECTURE}.md for an existing
    whole-project doc first (see project-context/README.md). BRD/PRD are human-authored
    only -- leave absent if missing. SRD/ARCHITECTURE are drafted automatically by
    srs-generator/technical-architecture-planner when missing, at status: DRAFT, and
    need human approval (project_docs.*.approved_by/approved_at in context-index.yaml)
    before any later work treats them as the project baseline -- draft them but do not
    block this work item on that approval.
 -> Requirements
 -> SRS/UI as required
 -> Requirement Verification
 -> Architecture / Technical Preparation
 -> ADR only if needed
 -> Technical Readiness
 -> Work Item Level Classification
 -> Sprint Handling Decision
 -> Sprint Planning only when required
 -> Epic/Stories/Tasks at minimum useful hierarchy
 -> Verification
 -> Implementation
 -> Review
 -> Auto QA
 -> Manual QA
 -> UAT as required
 -> Release Readiness
```

There is no separate PRD-generating skill: `business-requirement-analyzer` produces
BRD-shaped output and `srs-generator` produces SRS-shaped output; a project-wide PRD is
authored/maintained as its own doc (`project-context/PRD.md`) rather than machine-generated.

A new project does not automatically require an Epic or full Sprint Planning. Base the
decision on scope, dependencies, teams, risk, delivery complexity, and existing planning
artifacts, same as `new-feature.md`.
