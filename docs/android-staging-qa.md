# Android staging QA APK

[Android Staging QA APK](../.github/workflows/android-staging-qa.yml) builds an
**internal debug QA APK** for the staging backend at
`https://backend-staging-362e.up.railway.app`. `AppConfig` adds `/api/v1` to this
origin. The URL is public configuration; it is the only `dart-define`. Never
put credentials, tokens, SMTP settings, or OpenAI keys in build defines.
Use disposable synthetic QA accounts and data.

## Build contract

The workflow runs automatically when a push to `main` changes `frontend/**`
or this workflow file, including matching PR merges. `workflow_dispatch` also
allows a manual build. Backend-only changes do not trigger another APK build.
The workflow limits `GITHUB_TOKEN` to `contents: read`, checks out the triggering
commit, and disables persisted checkout credentials. Existing backend and
frontend CI workflows remain separate. APK builds and Railway deployments can
run in parallel; wait for the staging backend to be healthy before testing.

| Tool | Version / source |
| --- | --- |
| GitHub runner | `ubuntu-24.04` |
| Flutter / Dart | Flutter `3.44.8` stable, bundled Dart `3.12.2` |
| Java | Temurin JDK `17`, explicitly selected for Flutter |
| Gradle | `9.1.0`, from the checked-in Android wrapper |
| Android Gradle Plugin / Kotlin plugin | `9.0.1` / `2.3.20`, from `android/settings.gradle.kts` |
| Android platform / Build Tools | `android-36` / `36.0.0` |
| NDK / CMake | `28.2.13676358` / `3.22.1` |

JDK 17 and Gradle 9.1.0 match the
[AGP 9.0.1 compatibility requirements](https://developer.android.com/build/releases/agp-9-0-0-release-notes).
The platform and NDK match Flutter 3.44.8's defaults used by the existing app
Gradle configuration. Android command-line tools and accepted SDK licenses come
from the [GitHub Ubuntu runner](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md);
the workflow explicitly installs the listed SDK packages on that runner.

Dependencies are installed using `flutter pub get --enforce-lockfile`.
[Lockfile enforcement](https://dart.dev/tools/pub/cmd/pub-get#--enforce-lockfile)
fails if the checked-in `pubspec.lock` cannot satisfy `pubspec.yaml` or a hosted
package's content hash differs. The workflow also checks that the tracked
lockfile stays unchanged. Analysis, tests, and the build use `--no-pub` to avoid
another implicit dependency resolution.

Formatting, `flutter analyze`, and the full `flutter test` suite must pass before
the debug APK is built. The bundle is uploaded only after its APK checksum
passes verification. The upload allowlist contains exactly these three files:

| File | Purpose |
| --- | --- |
| `mealio-staging-qa-debug.apk` | Internal Android staging QA debug build |
| `SOURCE_COMMIT.txt` | Full source Git commit SHA, checked against the workflow run SHA |
| `SHA256SUMS` | SHA-256 checksum for the named APK |

The artifact is named `mealio-internal-staging-qa-debug-<full-commit-sha>` and
retained for **7 days**. Generated files stay under ignored `frontend/build/`;
do not add APKs, debug keys, keystores, or credentials to Git. Signing material
is not included in the upload.

This is a repeatable build process, **not a guarantee of byte-for-byte identical
APKs**. Debug signing keys, archive timestamps, the runner image, JDK patch
versions, and Actions major-version tags can change between runs. The checksum
identifies the APK from one particular run; it does not establish reproducibility
across separate builds.

## Build after merging frontend changes

After a matching merge into `main`, open the repository's **Actions** tab and
select **Android Staging QA APK**. Open the run for that merge and confirm its
full commit SHA is the revision intended for QA. Wait for formatting, analysis,
tests, APK build, checksum verification, and upload to succeed. If a step fails,
inspect its logs; do not substitute an artifact from another run.

For an optional manual build, click **Run workflow**, select `main`, and start
the run. [GitHub requires the workflow on the default branch](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
for manual dispatch; the operator needs repository write access.

The automatic run is a post-merge check. A person still verifies the downloaded
artifact and installs the APK on a phone before reporting device results.

## Install one verified run on one device

From the repository root, with Python 3.11+, authenticated `gh` CLI, `adb`, and
USB debugging available, first identify the intended run in **Actions → Android
Staging QA APK**. Copy its numeric run ID and full 40-character commit SHA. Run
`adb devices` to get the serial of the intended phone and authorize its USB
debugging prompt. Then run:

```bash
python3 scripts/install-android-staging-qa.py RUN_ID FULL_COMMIT_SHA DEVICE_SERIAL
```

Replace all three uppercase arguments with values from that specific run and
device. The helper never chooses the latest run. It requires the completed,
successful **Android Staging QA APK** run on `main` with the exact expected
`headSha`. Both `gh` calls explicitly select `github.com/Pavel404-dev/Mealio`,
regardless of `GH_HOST`, `GH_REPO`, or the current directory. It downloads only
the artifact named
`mealio-internal-staging-qa-debug-<full-commit-sha>` from that run into a fresh
temporary directory, verifies `SOURCE_COMMIT.txt` and the APK's `SHA256SUMS`,
checks that the selected serial is in the `device` state, and only then calls
`adb -s DEVICE_SERIAL install -r` for that APK. It reports an error and stops
if any check fails. It does not uninstall the app, clear data, select another
device, or keep the downloaded files. Re-run the same command to download and
verify a fresh copy if needed. An expired artifact must be rebuilt on `main`.

The APK comes from the workflow's checked-out commit and targets the staging
backend above. The SHA and checksum identify this specific CI bundle; the
helper does not build an APK locally.

## Optional manual download and verification

1. On the successful run's summary page, under **Artifacts**, download
   `mealio-internal-staging-qa-debug-<full-commit-sha>` before its 7-day expiry.
2. Extract the ZIP into a new directory outside the repository. All three files
   listed above should be together in that directory.
3. Open a terminal in the extracted directory and run:

   ```bash
   cat SOURCE_COMMIT.txt
   sha256sum --check SHA256SUMS
   ```

   Compare the full SHA with the run's source commit and the artifact name.
   The checksum command must exit successfully and print
   `mealio-staging-qa-debug.apk: OK`. On macOS, use
   `shasum -a 256 --check SHA256SUMS` instead.

Do not install the APK if the commit is unexpected or the checksum fails.
Download the complete bundle from the intended successful run again.

## Manual adb installation and removal

If installing without the helper, use an Android device with USB debugging
enabled and Android SDK Platform Tools (`adb`) available on your computer.
Connect the device and approve the USB debugging prompt. Verify the bundle as
above and confirm the chosen serial is in the `device` state. From the verified
bundle directory:

```bash
adb devices
adb -s <device-serial> install -r mealio-staging-qa-debug.apk
```

Replace `<device-serial>` with the intended device's serial from `adb devices`.
The unchanged application ID is `com.mealio.app`; this QA APK occupies the same
app slot as other Mealio builds with that ID. The staging origin uses HTTPS
directly, so `adb reverse` is unnecessary.

Android debug signing is for internal testing. **Debug keys can differ between
builds**, especially on fresh CI runners, and from a developer's local key.
`install -r` can preserve local data only when Android accepts the update.
A signature conflict (for example, `INSTALL_FAILED_UPDATE_INCOMPATIBLE`) can
require removing the existing app before installing this APK.

**Uninstalling deletes the app's local data, including locally stored sessions
and settings.** Only proceed if losing those data on the selected QA device is
acceptable. To resolve a signature conflict:

```bash
adb -s <device-serial> uninstall com.mealio.app
adb -s <device-serial> install mealio-staging-qa-debug.apk
```

To remove the QA app after testing, with the same local-data loss:

```bash
adb -s <device-serial> uninstall com.mealio.app
```

Uninstallation does not delete the account or data stored by the staging backend.

## Record device checks

After installation, record the device and environment, APK source commit, each
scenario actually checked, and its result. Include the Actions run ID, device
model/Android version and serial (redact the serial in public reports if needed),
staging backend status, and any failure message or screenshot with secrets
removed. State checks that were skipped or blocked, including an unavailable
staging backend. APK assembly alone is not a phone test. The APK build and
Railway backend deployment are independent; wait for a healthy staging backend
before checking flows that use it.

## Local frontend verification

With Flutter 3.44.8 and its bundled Dart available, run this single command from
the repository root:

```bash
bash scripts/check-frontend.sh
```

It runs the same frontend checks as [Frontend Tests](../.github/workflows/frontend-tests.yml)
in this order: tracked lockfile check, `flutter pub get --enforce-lockfile`,
`dart run tool/check_l10n.dart`, `flutter gen-l10n`,
`dart format --output=none --set-exit-if-changed .`, `flutter analyze --no-pub`,
and the full `flutter test --no-pub`. It stops at the first error and checks the
tracked `frontend/pubspec.lock` again on exit, including after a failed step.
Inspect an unexpected lockfile change before rerunning.

For an optional local APK build after that verification, run from `frontend/`:

```bash
flutter --version
flutter build apk --debug --no-pub \
  --dart-define=API_BASE_URL=https://backend-staging-362e.up.railway.app
```

The APK is written to `frontend/build/app/outputs/flutter-apk/app-debug.apk`.
The workflow's **Prepare and verify staging QA bundle** step documents the exact
packaging commands; its `GITHUB_SHA` comparison is specific to the CI run. A
local APK built from uncommitted source changes cannot be identified completely
by `git rev-parse HEAD` alone.

## Scope

This workflow does not change UI/UX, backend behavior, Railway infrastructure,
the application ID, or release signing. It does not configure production
signing, distribute a keystore, or publish to Play Store. SMTP, OpenAI, Android
App Links, and iOS/TestFlight are separate work. Broader manual mobile E2E is a
separate task; report only the device scenarios actually checked.
