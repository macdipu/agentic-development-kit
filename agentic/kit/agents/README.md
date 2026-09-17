# Agent catalog

**Skill** and **agent** are separate concepts in this kit, on purpose:

- A **skill** (`../skills/*/SKILL.md`) is a reusable capability/instruction set.
  The runtime discovers, sha256-pins, and gates skills by name
  (`../config/skill-registry.json`, `../config/permissions.json`,
  `../config/capabilities.json`; see `../runtime/python/agentic_runtime/registry.py`).
  See `../../SKILL-CATALOG.md` for the full list.
- An **agent** (this directory) is a domain persona that composes one or more
  existing skills and scopes which tasks it picks up. It is **not** a new
  runtime primitive: the orchestrator has no concept of "agent," only of
  skills and stage eligibility (which already supports several skills sharing
  one stage -- `implementation-agent` and `device-preview-agent` both run at
  `IMPLEMENTATION` today). An agent persona is invoked exactly like any other
  skill, via `task-start RUN_ID --skill <underlying-skill-name>`; the persona
  document narrows *which* tasks to pick up and *what scope* to stay inside.

Agents are not registered anywhere the way skills are -- no entries in
`skill-registry.json`/`permissions.json`/`capabilities.json`/`SKILL-CATALOG.md`.
Adding them there would re-conflate the two concepts this split exists to keep
apart, and `validate_structure.py` enforces those maps match discovered skill
directories exactly.

## Agents

| Agent | Domain | Composes |
|---|---|---|
| [`fe-agent`](fe-agent/AGENT.md) | FE | implementation-agent, web-preview-agent, user-flow-discovery-agent, requirement-ui-verifier, code-review-agent |
| [`mobile-agent`](mobile-agent/AGENT.md) | Mobile | implementation-agent, device-preview-agent, user-flow-discovery-agent, requirement-ui-verifier, code-review-agent |
| [`be-agent`](be-agent/AGENT.md) | BE | implementation-agent, api-contract-discovery-agent, code-review-agent, automated-qa-agent |
| [`db-integration-agent`](db-integration-agent/AGENT.md) | DB/Integration | implementation-agent, database-discovery-agent, api-contract-discovery-agent, code-review-agent |
| [`qa-agent`](qa-agent/AGENT.md) | QA | automated-qa-agent, test-baseline-agent, requirement-ui-verifier, epic-verifier, device-preview-agent, web-preview-agent |
| [`security-devops-agent`](security-devops-agent/AGENT.md) | Security/DevOps | code-review-agent, automated-qa-agent, brownfield-risk-analyzer, change-impact-analyzer, implementation-agent |

`fe-agent` and `mobile-agent` are split deliberately: they compose different
preview skills (`web-preview-agent` vs `device-preview-agent`), not the same
one under two names.

## Task pickup

`../templates/task.md` carries a `## Category` field (`FE`, `Mobile`, `BE`,
`DB/Integration`, `QA`, `Security/DevOps`, or `Documentation`), set by
`task-breakdown-agent`. The matching persona above picks up a task by that
field; see `../workflows/routing.md` for how this fits the wider routing flow.
