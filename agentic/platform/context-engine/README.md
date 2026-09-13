# Context Engine

The local runtime fingerprints caller-selected context/source files and checks them before downstream work. Dirty changes and deletions invalidate that scope; unrelated files do not. Automatic scope selection, dependency discovery, confidence review, and semantic freshness remain specialist/adapter responsibilities.

See the [runtime capability matrix](../../runtime/README.md#capability-matrix) and [production checklist](../agent-harness/production-readiness.md).
