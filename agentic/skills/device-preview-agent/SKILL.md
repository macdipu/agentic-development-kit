---
name: device-preview-agent
description: Build, launch, and visually verify mobile apps in Android emulators, iOS simulators, or a requested connected device. Use for in-device previews, hot reload, screenshots, and targeted UI smoke checks with Flutter or the project's native tooling.
---

# Device Preview Agent

## Scope and inputs

Deliver a running preview of the requested app and screen on an identified target, with evidence of what was actually inspected. Load the work item and relevant project context first. Resolve the app directory, framework/toolchain, entrypoint, flavor or scheme, application ID, requested screen, target platform, and existing run instructions from that scope.

Reuse the project's version manager, build scripts, environment, and test fixtures. Do not guess package IDs, credentials, build variants, or backend configuration. If multiple plausible variants affect the preview, request the missing choice while completing independent discovery.

## Procedure

1. **Select a target.** Honor the user's device choice. Otherwise prefer a compatible running virtual device, then an existing compatible virtual device that can be booted. Record its serial or UDID and OS version. Re-list after boot; an emulator configuration name is not necessarily its runtime device ID. Use an explicit target on every device command. If several targets remain equally suitable, choose one and report it; do not install on every connected device. Use physical devices only when requested or already authorized.
2. **Check readiness.** Confirm required local tools and the selected runtime are available. Read only the applicable reference: [Android](references/android.md) or [iOS](references/ios.md). If the runtime is absent, report the exact missing component and perform setup only within the user's authorized scope. Do not erase devices, clear app data, uninstall apps, or change signing identities to repair a preview without authorization for that action.
3. **Build and launch.** Use the existing debug/development run path and exact variant. Prefer an existing matching development session for hot reload; use restart or rebuild when the change requires it. Keep long-running build or run commands in a managed session so progress and failures remain visible. Confirm device readiness and successful installation and launch separately. A build success alone is not a preview.
4. **Inspect the requested screen.** Bring the emulator or Simulator window forward using the available permitted UI tooling. Navigate using observed UI, an existing project deep link, or a focused UI test. Do not invent coordinates or unsupported simulator tap commands. Check the requested behavior and obvious clipping, overflow, keyboard/safe-area obstruction, error overlays, and navigation failures. Expand to other screen sizes or themes only when the change or request warrants it.
5. **Capture evidence.** Save screenshots to a task-specific local artifact directory, then open them with an available image viewer and inspect them. Record target, screen, variant, source revision and relevant working-tree changes, and artifact paths. If visual inspection tools are unavailable, report launch/capture evidence with visual verification marked incomplete. Use test data; avoid exposing credentials or private data in logs and screenshots.
6. **Handle failures and handoff.** Distinguish toolchain, boot, build, install, launch, backend, and UI failures. Inspect the relevant error before retrying. Follow the harness retry budget; when none is configured, allow at most two retries after the initial attempt, each supported by a concrete change or new evidence. Bound device readiness waits (default two minutes) and stop with diagnostics when exceeded. A slow build with continuing progress is not a reason to restart it. Return to the orchestrator for implementation fixes outside the preview scope.

Leave the requested app and preview window running for the user. Report any live development session and whether hot reload remains available. Stop only temporary helper processes owned by this task; do not shut down unrelated devices or shared development servers. Record start/end events through the harness when available; do not estimate timing.

## Result contract

Return:

- `status`: `PREVIEW_READY`, `PARTIAL`, or `BLOCKED`.
- `target`: platform, device name, serial/UDID, OS, virtual or physical.
- `build`: app directory, variant, entrypoint/scheme, revision and working-tree qualification, commands used.
- `checks`: build, install, launch, requested screen, and visual inspection, each with an observed result or reason not checked.
- `evidence`: screenshot/log paths, observations, and reproduction steps for any defect.
- `session`: whether the preview is still running, development session identifier if available, and reload/relaunch instructions.
- `blocking_issues`, `open_questions`, and `recommended_next_step`.

Use `PREVIEW_READY` only when the requested screen is running and visually inspected. Use `PARTIAL` for a launch with incomplete screen or visual verification. A preview is evidence for implementation or QA; it does not imply manual QA, UAT, or release approval.

## Runtime handoff

Use the shared [handoff contract](../RESULT-CONTRACT.md) when submitting results to the reference runtime. Put the specialized fields and verdict described above inside `outputs`; retain evidence and blockers in the envelope.
