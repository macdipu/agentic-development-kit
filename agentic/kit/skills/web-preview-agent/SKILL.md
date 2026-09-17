---
name: web-preview-agent
description: Build, launch, and visually verify web apps in a browser. Use for local dev-server previews, hot reload, screenshots, and targeted UI smoke checks with the project's existing web tooling.
---

# Web Preview Agent

## Scope and inputs

Deliver a running preview of the requested web app and page/route on a local
dev server, opened in a browser, with evidence of what was actually inspected.
Load the work item and relevant project context first. Resolve the app
directory, framework/toolchain, entrypoint, build/dev command, port, requested
page/route, and existing run instructions from that scope.

Reuse the project's package manager, existing dev/build scripts, environment,
and test fixtures. Do not guess ports, environment variables, credentials, or
backend configuration. If multiple plausible dev-server variants affect the
preview (e.g. multiple apps in a monorepo), request the missing choice while
completing independent discovery.

## Procedure

1. **Select a target.** Honor the user's browser choice if any; otherwise use
   an available browser automation tool (a Chrome extension/CDP tool, or an
   equivalent already available in the session). Identify the exact route/page
   to inspect and the port/URL the dev server will serve.
2. **Check readiness.** Confirm the project's dev/build command is registered
   (`agentic/kit/config/allowed-commands.json`, permission `preview`) and the
   package manager/runtime is available. Do not install global tooling or
   change project dependencies to repair a preview without authorization for
   that action.
3. **Build and launch.** Use the existing dev-server command and exact
   variant/port. Prefer an existing running dev server for hot reload; restart
   only when the change requires it. Keep long-running dev-server commands in
   a managed session so progress and failures remain visible. Confirm the
   server is actually serving before navigating -- a build success alone is
   not a preview.
4. **Inspect the requested page.** Navigate the browser to the requested
   route. Check the requested behavior and obvious layout breakage, console
   errors, failed network requests, and unstyled/broken content. Expand to
   other viewport sizes only when the change or request warrants it.
5. **Capture evidence.** Save a screenshot to a task-specific local artifact
   directory, then inspect it. Record the route, viewport, source revision and
   relevant working-tree changes, and artifact paths. If visual inspection
   tools are unavailable, report launch/capture evidence with visual
   verification marked incomplete. Use test data; avoid exposing credentials
   or private data in logs, console output, and screenshots.
6. **Handle failures and handoff.** Distinguish toolchain, dependency-install,
   build, dev-server-start, network, and UI failures. Inspect the relevant
   error before retrying. Follow the harness retry budget; when none is
   configured, allow at most two retries after the initial attempt, each
   supported by a concrete change or new evidence. Return to the orchestrator
   for implementation fixes outside the preview scope.

Leave the requested dev server and browser session running for the user.
Report whether hot reload remains available. Stop only temporary helper
processes owned by this task; do not shut down unrelated or shared dev
servers. Record start/end events through the harness when available; do not
estimate timing.

## Result contract

Return:

- `status`: `PREVIEW_READY`, `PARTIAL`, or `BLOCKED`.
- `target`: framework, dev-server command, port/URL, route/page inspected.
- `build`: app directory, variant, revision and working-tree qualification, commands used.
- `checks`: dependency install, build, dev-server start, requested page, and visual inspection, each with an observed result or reason not checked.
- `evidence`: screenshot/log paths, observations, and reproduction steps for any defect.
- `session`: whether the dev server is still running, session identifier if available, and reload/relaunch instructions.
- `blocking_issues`, `open_questions`, and `recommended_next_step`.

Use `PREVIEW_READY` only when the requested page is served and visually
inspected. Use `PARTIAL` for a launch with incomplete page or visual
verification. A preview is evidence for implementation or QA; it does not
imply manual QA, UAT, or release approval.

## Runtime handoff

Use the shared [handoff contract](../RESULT-CONTRACT.md) when submitting
results to the reference runtime. Put the specialized fields and verdict
described above inside `outputs`; retain evidence and blockers in the
envelope.
