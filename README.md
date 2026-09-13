# Agentic Development Kit

A reusable set of 34 specialist skills, SDLC workflows, and a local Python reference harness for coordinating software work with explicit evidence and approval gates.

Start with [adoption](agentic/ADOPTION.md), browse the [skill catalog](agentic/SKILL-CATALOG.md), or read the [runtime guide](agentic/runtime/README.md). The full [workflow guide](agentic/README.md) explains context reuse, requirements, conditional planning, implementation, QA, and release readiness.

```sh
sh agentic/scripts/validate-kit.sh
python3 agentic/examples/runtime-demo.py
```

Validation uses Python 3.10+ and its standard library. The demo is isolated and synthetic; it neither invokes a model nor launches an app. For mobile app previews, use [device-preview-agent](agentic/skills/device-preview-agent/SKILL.md).

The harness enforces local workflow rules for trusted adapters. Production execution, authenticated human identity, process isolation, and external service integrations require additional infrastructure; see the [capability matrix](agentic/runtime/README.md#capability-matrix).
