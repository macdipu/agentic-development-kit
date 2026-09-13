# Audit Log

Run mutations atomically append SQLite checkpoint/audit records; tool reservations and outcomes are durable local records. Payloads use best-effort redaction. The database is operator-writable; immutable retention and tamper resistance require external infrastructure.

See the [runtime capability matrix](../../runtime/README.md#capability-matrix) and [production checklist](../agent-harness/production-readiness.md).
