# Feature artifact storage

Each work item gets one folder here, named by its canonical work-item ID (the ID assigned
during intake, e.g. `FEATURE-042`, `CR-013`; the same id the classifier records as
`work_item_id`, which the runtime uses to check planning files):

```text
agentic/data/project-context/features/<WORK-ITEM-ID>/
├── WORK-ITEM.md          # canonical item from prompt-intake-adapter (prompt-first intake)
├── context.yaml          # optional, module-context.yaml-shaped snapshot for this feature
├── BRD.md                # copy or reference of the originating BRD/FEATURE/CR doc (optional)
├── SRS.md                # from srs-generator
├── ARCHITECTURE.md       # feature HLD, from technical-architecture-planner
├── TECH-SPEC.md          # feature LLD, from technical-spec-generator
├── adr/
│   └── ADR-XXX-title.md  # from adr-generator, only for significant decisions
├── EPIC.md               # from sprint-planner, EPIC_STORY_TASK only
├── stories/
│   └── STORY-XXX.md      # from sprint-planner, EPIC_STORY_TASK / STORY_TASK
└── tasks/
    └── TASK-XXX.md       # from task-breakdown-agent (any hierarchy except existing-task)
```

Templates for each file type live in `agentic/kit/templates/` (`brd.md`, `srs.md`, `feature-hld.md`,
`feature-lld.md`, `adr.md`, `task.md`).

Whole-app/whole-project BRD, PRD, SRD, ARCHITECTURE live one level up, at
`agentic/data/project-context/{BRD,PRD,SRD,ARCHITECTURE}.md` (see `../README.md`), not
in a feature folder. SRD/ARCHITECTURE are generated there automatically when missing and
gated on human approval; BRD/PRD are human-authored only. A feature's own
`BRD.md`/`SRS.md`/`ARCHITECTURE.md` here should reference the project-wide doc rather
than restate it.

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
