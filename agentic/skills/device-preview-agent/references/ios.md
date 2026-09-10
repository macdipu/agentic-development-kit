# iOS preview

iOS Simulator requires macOS, a usable Xcode installation, and an installed compatible simulator runtime. These are command patterns; replace placeholders with discovered values and quote arguments. Use installed `xcrun simctl help <command>` and `xcodebuild -help` for version-specific details.

## Target and readiness

```sh
xcode-select -p
xcrun simctl list devices available
xcrun simctl bootstatus <udid> -b
open -a Simulator
```

Select a compatible existing device by UDID. `bootstatus -b` boots if needed and waits for readiness; monitor it in a managed session with the skill's deadline. Select that same device in the Simulator UI. Use its UDID for subsequent commands instead of the ambiguous `booted` alias. Missing runtimes and an incorrectly selected Xcode are setup blockers; do not silently change the system's developer directory or download runtimes.

## Flutter

```sh
flutter devices
flutter run -d <simulator-udid>
```

Use the repository's pinned Flutter wrapper, entrypoint, flavor, and environment arguments. Keep an interactive managed run session for hot reload/restart. Confirm the device ID from Flutter discovery. Native changes require the project's rebuild path.

## Native or other frameworks

Prefer the established framework run script. For native Xcode projects, discover the workspace/project, shared scheme, configuration, and available destinations first. A workspace example is:

```sh
xcodebuild -list -workspace <workspace-path>
xcodebuild -showdestinations -workspace <workspace-path> -scheme <scheme>
xcodebuild -workspace <workspace-path> -scheme <scheme> -configuration Debug -destination 'platform=iOS Simulator,id=<udid>' -derivedDataPath <task-build-directory> build
xcrun simctl install <udid> <simulator-app-path>
xcrun simctl launch <udid> <bundle-id>
```

Use `-project` when the repository uses a project without a workspace. Resolve the `.app` and bundle ID from the selected build's output/settings. An iPhone device build or IPA is not interchangeable with a Simulator build. Do not change provisioning or production signing to make a Simulator preview work.

## Visual evidence and diagnostics

```sh
xcrun simctl io <udid> screenshot <artifact-directory>/ios-preview.png
```

Navigate with available permitted Simulator UI automation, an existing deep link, or project UI tests. `simctl` installation and launch do not provide a general tap/navigation interface. Inspect the saved PNG after the requested screen is stable. Use Xcode or the project's existing app log tooling for launch failures; scope evidence to the app and relevant interval.

For a requested physical iPhone, use the repository's established device deployment path and identify the device explicitly. `simctl` does not deploy to physical devices. Report missing trust, Developer Mode, signing, or provisioning as concrete blockers and preserve existing signing configuration.

Command semantics checked against installed Xcode `simctl help bootstatus`, `io`, `install`, and `launch`. Further guidance: [Apple Simulator overview](https://developer.apple.com/videos/play/wwdc2019/418/), [Flutter CLI](https://docs.flutter.dev/reference/flutter-cli).
