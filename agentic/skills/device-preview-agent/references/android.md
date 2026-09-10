# Android preview

These are command patterns, not a batch script. Replace angle-bracket placeholders with discovered values, quote arguments, and run from the correct app directory. Use the project's pinned tools and installed command help when syntax differs.

## Target and readiness

```sh
adb devices -l
emulator -list-avds
emulator -avd <avd-name>
adb -s <serial> shell getprop sys.boot_completed
```

Resolve `adb` and `emulator` from the configured Android SDK if absent from PATH. Start an existing AVD only if needed, in a managed process session. Re-list devices to obtain its serial; do not assume `emulator-5554`. Poll boot completion until `1` within the skill's deadline. An `offline` or `unauthorized` target is not ready; a physical device may need the user to unlock it and accept its debugging prompt. Avoid resetting the shared ADB server as a first repair.

## Flutter

```sh
flutter devices
flutter emulators
flutter emulators --launch <emulator-id>
flutter run -d <device-id>
```

Choose either Flutter or the SDK emulator launch path, not both. Use `fvm flutter` when the repository uses FVM. Preserve project-required `--flavor`, `--target`, and environment arguments. Keep `flutter run` in an interactive managed session for `r` (hot reload) or `R` (hot restart); native/plugin changes may require a rebuild. Recheck the screen after reload.

## Native or other frameworks

Use the repository's Gradle wrapper or established framework run script and select the exact development variant. For a native APK, a typical path is:

```sh
./gradlew :app:assembleDebug
adb -s <serial> install -r <apk-path>
adb -s <serial> shell am start -W -n <application-id>/<launcher-activity>
```

The module/task above is illustrative; discover the actual task and artifact. Use a simulator-compatible ABI. For split APKs use the project's supported install path. Resolve the application ID and launcher activity from the selected variant's manifest/artifact. If updating fails due to signatures or a downgrade, report it; do not uninstall and lose data automatically.

## Visual evidence and diagnostics

```sh
adb -s <serial> exec-out screencap -p > <artifact-directory>/android-preview.png
adb -s <serial> logcat -d -t 200
```

Capture after reaching a stable requested screen and inspect the PNG. Scope logs to the app/process and relevant time window when possible; do not publish unrelated device logs. UI interaction can use available device tooling or observed Android UI hierarchy; screenshots alone do not establish interactive behavior. If the app cannot reach a development backend, inspect the project's device networking setup rather than assuming the host's `localhost` is reachable from the guest.

Sources: [Android emulator command line](https://developer.android.com/studio/run/emulator-commandline), [ADB](https://developer.android.com/tools/adb), [Flutter CLI](https://docs.flutter.dev/reference/flutter-cli).
