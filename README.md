# Agentic Development Kit

A reusable set of 34 specialist skills, SDLC workflows, and a local Python reference harness for coordinating software work with explicit evidence and approval gates.

Start with [adoption](agentic/ADOPTION.md), browse the [skill catalog](agentic/SKILL-CATALOG.md), or read the [runtime guide](agentic/kit/runtime/README.md). The full [workflow guide](agentic/README.md) explains context reuse, requirements, conditional planning, implementation, QA, and release readiness.

```sh
sh agentic/kit/scripts/validate-kit.sh
python3 agentic/kit/examples/runtime-demo.py
python3 agentic/kit/examples/legacy-delivery.py
```

Validation uses Python 3.10+ and its standard library, including behavioral runtime and adoption tests. Both examples use isolated fixtures; the legacy example reproduces a failing baseline and verifies a source fix with real tests and synthetic approvals. Neither invokes a model nor deploys. For mobile app previews, use [device-preview-agent](agentic/kit/skills/device-preview-agent/SKILL.md).

Installation supports instruction-only and local-harness modes, preserves host configuration, and includes a `doctor` command. The [production readiness contract](agentic/kit/runtime/production-readiness.md) adds staged evidence checks for host deployment infrastructure.

The harness enforces local workflow rules for trusted adapters. Production execution, authenticated human identity, process isolation, and external service integrations require additional infrastructure; see the [capability matrix](agentic/kit/runtime/README.md#capability-matrix).
