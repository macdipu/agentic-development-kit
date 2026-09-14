# Specialist handoff contract

Every specialist returns this envelope to the orchestrator. Keep domain-specific fields in `outputs` and use `outputs.verdict` for specialized readiness or planning verdicts.

```json
{
  "status": "READY",
  "evidence": ["path/to/artifact.md#acceptance-criteria"],
  "blocking_issues": [],
  "open_questions": [],
  "recommended_next_step": "Review the technical design",
  "outputs": {"verdict": "TECHNICAL_READY"}
}
```

- `READY`: this specialist's bounded responsibility is complete and supported by evidence. It is not human approval.
- `PARTIAL`: usable findings exist, but requested checks or inputs remain incomplete.
- `BLOCKED`: a specific unresolved dependency prevents completion.
- Device preview may use `PREVIEW_READY` after launch and visual inspection; preserve its detailed target/build/check/session fields inside `outputs` when submitting to the runtime.
- `evidence`, `blocking_issues`, and `open_questions` are arrays of nonempty strings. Evidence references should identify a file/section, test command and result artifact, or observable source. Do not put credentials or full sensitive logs in the envelope.
- `READY` and `PREVIEW_READY` require evidence and no blocking issues. An unresolved question may remain only if it does not prevent this responsibility's completion; explain that in `outputs`.
- Use stable requirement, task, defect, and artifact identifiers from the work item. Distinguish observed facts, inferences, and unknowns. Link changed artifacts to the requirements and checks they address.

Load only the relevant project context. Prefer reuse and incremental discovery. Return to the orchestrator for routing; do not expand scope or infer business rules or human approval. Record timing through the harness, when available, rather than estimating it.

The runtime validates this envelope's shape. It cannot prove that evidence is truthful or that a business requirement is satisfied; reviewers remain responsible for those judgments.
