# Feature artifact storage

Each work item that reaches requirements stage or beyond gets one folder here, named by its
canonical work-item ID (the ID assigned during intake, e.g. `FEATURE-042`, `CR-013`):

```text
agentic/data/project-context/features/<WORK-ITEM-ID>/
├── context.yaml          # optional, module-context.yaml-shaped snapshot for this feature
├── BRD.md                # copy or reference of the originating BRD/FEATURE/CR doc (optional)
├── SRS.md                # from srs-generator
├── ARCHITECTURE.md       # from technical-architecture-planner
├── TECH-SPEC.md          # from technical-spec-generator
├── adr/
│   └── ADR-XXX-title.md  # from adr-generator, only for significant decisions
└── tasks/
    └── TASK-XXX.md       # from task-breakdown-agent
```

Templates for each file type live in `agentic/kit/templates/` (`brd.md`, `srs.md`, `architecture.md`,
`tech-spec.md`, `adr.md`, `task.md`).

Rules:

- The original intake document (`FEATURE.md`, `CR.md`, `BUG.md`, `HOTFIX.md`, or `BRD.md`)
  stays wherever the author placed it (commonly the repo root); `document-intake-adapter`
  records its path rather than moving it. Copy it into this folder only if you want a
  point-in-time snapshot alongside the derived artifacts.
- Only create the files a work item actually needs — a small CR may produce no SRS or
  architecture doc at all. Do not create empty placeholders.
- Update `context-index.yaml`'s `features` map with the folder path and status when a
  feature folder is created or its status changes.
- File existence is not approval. Status fields inside each doc (Draft/Proposed/READY/etc.)
  track drafting state, not human sign-off.
- After adding or removing files under `agentic/`, regenerate the kit manifest:
  `python3 agentic/kit/scripts/validate_structure.py --write-manifests` (kit repo only, not
  required in a host project that has copied the kit in).
