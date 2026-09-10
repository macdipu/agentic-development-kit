# Prompt-first example

Developer:
`Start feature: Add Gift Transfer and reuse the existing transfer, beneficiary, charge, OTP and TPIN flows.`

The system:
1. Normalizes the prompt into a canonical feature work item.
2. Loads project context.
3. Resolves affected modules.
4. Finds analogous implementation.
5. Runs the required SDLC stages and skills.

## Device preview

Developer:
`Run this app on an Android emulator and show the updated home screen. Keep it running for preview.`

The orchestrator selects `device-preview-agent`, reuses the app's run configuration, selects an explicit emulator target, launches the app, inspects the home screen, and returns screenshot evidence and session details. Use the same flow for an iOS Simulator request. If only launch succeeds, report a partial preview rather than claiming visual verification.
