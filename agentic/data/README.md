# Kit data

Everything under `agentic/data/` is per-project: it did not come with the kit and is not part of
it. The kit (`agentic/kit/skills/`, `templates/`, `workflows/`, `config/`, `scripts/`,
`runtime/hooks/`, `runtime/python/`) is the same in every project that adopts it and only changes
when you upgrade the kit itself. This folder is where that kit accumulates state, logs, and
generated documents as the project runs. Do not add skills, templates, or config here; do not put
generated docs or state in the kit folders above this one.

```text
data/
└── project-context/     tracked   discovery cache + every work item's folder (features/<id>/)
```

Runtime state is not here: it lives with the handoff notes under the repo-root `.agent/`
folder (see below).

## project-context/

- `project.yaml` — project identity (name, type). Set once by `agentic-init` / `init_project.py`.
- `context-index.yaml` — index of what context is cached: module discovery status and the
  `features` map (work-item ID -> status/path).
- `modules/`, `integrations/`, `shared-components/`, `tests/` — discovered/reconstructed context
  for brownfield work, one file per module (see `agentic/kit/templates/module-context.yaml`).
- `features/<WORK-ITEM-ID>/` — generated docs for one work item (BRD/SRS/ARCHITECTURE/TECH-SPEC,
  `adr/`, `tasks/`). See `features/README.md` for the exact layout and which skill writes what.
- `kit-runtime.json` — this repo's own module-context entry for the kit's runtime engine
  (this repo dogfoods the kit on itself; a host project's copy starts without it).

All of this is tracked in git — it's the project's accumulated context, not a cache you'd want to
lose. Refresh only the affected module/feature scope when it goes stale; don't re-discover the
whole repository for every task.

## Work items

Every work item -- feature, CR, bug, hotfix, technical change, or a small task -- lives in
one folder, `project-context/features/<WORK-ITEM-ID>/`: the canonical item
(`WORK-ITEM.md` for prompt-first intake; a document-first item keeps its source file and
records its path), then whatever the lifecycle derives (requirements, design, `EPIC.md`,
`stories/`, `tasks/`). There is no separate work-items folder.

## Runtime state (`.agent/`)

The runtime's operating state lives outside `agentic/data/`, beside the cross-agent handoff notes:

```text
.agent/
├── HANDOFF.md                       local      copy of the newest handoff note
├── sessions/*.md                    committed  one record per session
├── state/                           committed  append-only (added, never edited)
│   ├── runs/<run_id>/events/*.json            run ledger; state = replay of events
│   ├── claims/<run_id>/*.json                 which clone holds the run
│   └── handoffs/*.md                          handoff notes
└── local/                           ignored    active-task pointer, clone id, route cache
(each runs/<run_id>/ also holds an ignored .lock and .cache.json beside events/)
```

Committed files travel with the project's normal push/pull and never conflict. The
`SessionStart` hook checks the local pointer and the run store for anything left running
-- here or handed off from another machine (`cli.py resume RUN_ID` continues it) -- and
reports other clones' claims and commits waiting upstream.
