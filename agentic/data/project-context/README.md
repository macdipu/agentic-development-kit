# Project-context layout

```text
agentic/data/project-context/
├── project.yaml          # project identity, repos, modules, integrations
├── context-index.yaml    # freshness/status index for modules and features
├── kit-runtime.json      # kit's own module-context snapshot
├── BRD.md                # whole-app/whole-project BRD, optional
├── PRD.md                # whole-app/whole-project PRD, optional
├── SRD.md                # whole-app/whole-project SRD/SRS, optional
└── features/<WORK-ITEM-ID>/   # per-feature/CR/bug artifacts, see features/README.md
```

## Project-wide vs feature-scoped docs

- `BRD.md`, `PRD.md`, `SRD.md` at this root describe the whole application/project —
  cross-feature business objectives, product scope, and system-wide requirements that
  outlive any single work item.
- A feature/CR/bug's own `BRD.md`/`SRS.md` under `features/<WORK-ITEM-ID>/` scope those
  same concerns to that work item, and should reference the project-wide doc (via
  `## References`) rather than restate it.
- Templates: `agentic/kit/templates/brd.md`, `srs.md` (used for both PRD- and SRD-shaped
  content; the kit does not distinguish a separate PRD template).
- Same rule as feature docs: only create the project-wide file when the project actually
  has one — do not create empty placeholders. If the project has no whole-app BRD/PRD/SRD,
  leave these absent.
- When a project-wide doc is added, removed, or changes materially, update
  `context-index.yaml`'s `project_docs` map (path + status), mirroring how `features` are
  tracked.
