# Project-context layout

```text
agentic/data/project-context/
├── project.yaml          # project identity, repos, modules, integrations
├── context-index.yaml    # freshness/status index for modules and features
├── kit-runtime.json      # kit's own module-context snapshot
├── BRD.md                # whole-app/whole-project BRD, optional, human-authored only
├── PRD.md                # whole-app/whole-project PRD, optional, human-authored only
├── SRD.md                # whole-app/whole-project SRD/SRS, generated + human-approved
├── ARCHITECTURE.md       # whole-app/whole-project architecture, generated + human-approved
└── features/<WORK-ITEM-ID>/   # per-feature/CR/bug artifacts, see features/README.md
```

## Project-wide vs feature-scoped docs

- `BRD.md`, `PRD.md`, `SRD.md`, `ARCHITECTURE.md` at this root describe the whole
  application/project — cross-feature business objectives, product scope, and
  system-wide requirements/design that outlive any single work item.
- A feature/CR/bug's own `BRD.md`/`SRS.md`/`ARCHITECTURE.md` under
  `features/<WORK-ITEM-ID>/` scope those same concerns to that work item, and should
  reference the project-wide doc (via `## References`) rather than restate it.
- Templates: `agentic/kit/templates/brd.md`, `srs.md` (used for both PRD- and SRD-shaped
  content; the kit does not distinguish a separate PRD template), `architecture.md`.

### BRD.md / PRD.md — human-authored only

- Only create these when the project actually has one — do not create empty
  placeholders or draft business/product intent on a human's behalf. If the project has
  no whole-app BRD/PRD, leave both absent.

### SRD.md / ARCHITECTURE.md — generated, gated on human approval

These two are derived from BRD/requirements the same way their feature-scoped
counterparts are, so they get generated automatically instead of staying absent:

- When a work item reaches REQUIREMENTS stage and root `SRD.md` does not exist yet,
  `srs-generator` drafts it (in addition to the feature's own `SRS.md`) from the same
  verified requirements, at `status: DRAFT`.
- When a work item reaches TECHNICAL stage and root `ARCHITECTURE.md` does not exist
  yet, `technical-architecture-planner` drafts it (in addition to the feature's own
  `ARCHITECTURE.md`) from the same verified design, at `status: DRAFT`.
- A drafted root doc is not a baseline. Per AGENTS.md #10 ("never infer human
  approval"), no skill may mark its own draft `APPROVED` or treat it as authoritative.
  Downstream work may reference it as a proposal, but the feature must not be blocked
  waiting on it unless the workflow says so — surface it as an open question and keep
  moving.
- A human approves by recording `approved_by`/`approved_at` on the doc's
  `context-index.yaml` entry (see below) after review. Only then does later work treat
  it as the whole-project baseline.
- Once `SRD.md`/`ARCHITECTURE.md` exist and are `APPROVED`, treat them like `BRD.md` —
  only regenerate/update when requirements or design materially change, and reference
  rather than restate them from feature docs.
- When a project-wide doc is added, removed, or changes materially, update
  `context-index.yaml`'s `project_docs` map (path + status + approval), mirroring how
  `features` are tracked.
