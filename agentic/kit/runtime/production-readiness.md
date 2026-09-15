# Staged production readiness

Production autonomy is introduced through four explicit stages. The local runtime
continues to reject production tool registration and execution. This contract helps
a host project prepare and review its external infrastructure.

| Stage | Authorized scope to establish externally | Required evidence added at this stage |
|---|---|---|
| OBSERVE | Read-only production inspection | Scoped read identity, protected audit, data handling and retrieval controls |
| PREPARE | Branches, tests, release artifacts | Isolated workers, credential/network restrictions, verification, artifact integrity |
| APPROVED_EXECUTION | Exact change approved for an environment | Authenticated approval, durable jobs, effect reconciliation, health checks, rollback, kill switch, alerts, backup/restore |
| BOUNDED_AUTONOMY | Explicit operations under standing authorization | Limits, canary rollout, expiry/revalidation, bounded impact |

Every stage includes all earlier controls. An existing local `--by` approval string
is not evidence of authenticated production identity.

## Enforcing adapter requirements

An execution adapter must authenticate the actor and verify approval against the
exact artifact digest, environment, operation, and expiry immediately before an
effect. Separate credentials for observation, preparation, and deployment.

Workers need OS/container isolation, restricted secrets and network access, bounded
execution, durable job ownership/leases, and a kill switch. Persist an operation ID
before invoking an external service. On an interrupted or ambiguous response,
reconcile observed external state before retrying. A database reservation alone
does not provide exactly-once effects.

Deploy progressively with health checks and an impact limit. Exercise rollback
or compensating actions with realistic data, including irreversible migrations.
Keep audit records outside worker write access, monitor failed/late operations,
alert an owner, and test database/artifact backup restoration.

Standing authorization must specify allowed operation IDs, target scope, maximum
actions, duration, affected resources, and expiry. Revalidate after code, policy,
identity, or environment changes. Establish these integrations in the host project
and measure them in staging before enabling production execution.

## Evidence contract and checker

Copy [the template](../templates/production-readiness.json) into the host's artifact
directory and fill it with actual reviewed evidence. Each required control uses:

```json
{
  "status": "VERIFIED",
  "reviewer": "reference-to-authenticated-review",
  "verified_at": "2026-09-15T00:00:00+00:00",
  "expires_at": "2026-09-16T00:00:00+00:00",
  "environment": "the-target-environment",
  "change_sha256": "64-lowercase-hex-characters",
  "operations": ["an-explicit-operation-id"],
  "path": "evidence/report.md",
  "sha256": "64-lowercase-hex-characters"
}
```

Paths are relative to the readiness JSON file. Evidence must exist within that
directory, be nonempty, match its SHA-256 hash, and be current. Each control must
match the top-level environment, change digest, and operations. A changed artifact
therefore requires renewed control evidence. The empty template deliberately fails.

```sh
python3 agentic/kit/runtime/python/agentic_runtime/cli.py production-check --file path/to/readiness.json
```

Exit 0 means `EVIDENCE_COMPLETE`; missing, stale, altered, or mismatched evidence
returns `BLOCKED` and exit 1. Both outcomes return `deployment_authorized: false`.
The checker verifies local evidence structure, hashes, scope, and dates. It cannot
authenticate reviewer claims or prove that an external isolation/rollback system
works. An enforcing deployment adapter remains responsible for those checks.

## Kit evidence

- Behavioral runtime, hook, installer, rollback, and readiness-contract regression
  tests are included and run by `sh agentic/kit/scripts/validate-kit.sh`.
- The repository supplies CI configuration; hosted results must be checked after push.
- The legacy-delivery fixture runs real checks, uses synthetic approvals, and performs
  no deployment.
- No shared worker service, cloud account, authenticated approval backend, production
  deployment adapter, or immutable audit service is bundled.
