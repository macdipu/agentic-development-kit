# Greenfield

```text
BRD / PRD / Prompt / Feature Doc
 -> Check agentic/data/project-context/{BRD,PRD,SRD}.md for an existing whole-project
    doc before generating one; generate only what's missing (see project-context/README.md)
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
