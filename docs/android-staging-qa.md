# Android staging QA APK

[Android Staging QA APK](../.github/workflows/android-staging-qa.yml) builds an
**internal debug QA APK** for the staging backend at
`https://backend-staging-362e.up.railway.app`. `AppConfig` adds `/api/v1` to this
origin. The URL is public configuration; it is the only `dart-define`. Never
put credentials, tokens, SMTP settings, or OpenAI keys in build defines.
Use disposable synthetic QA accounts and data.

## Build contract

The workflow has only `workflow_dispatch`, with no automatic push or PR trigger,
and limits `GITHUB_TOKEN` to `contents: read`. It checks out the full source
commit selected by the manual run and disables persisted checkout credentials.
Existing backend and frontend CI workflows remain separate.

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

## Run manually after merge

These are user actions after the reviewed workflow has been merged into `main`.
[GitHub requires the workflow on the default branch](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
for manual dispatch; the operator needs repository write access.

1. Open the repository's **Actions** tab and select **Android Staging QA APK**.
2. Click **Run workflow**, select `main`, and click **Run workflow** to start it.
3. Open the new run and record its full commit SHA. Confirm that this is the
   reviewed source revision intended for QA.
4. Wait for formatting, analysis, tests, APK build, checksum verification, and
   upload to finish successfully. If a step fails, inspect that run's logs;
   do not substitute an artifact from another run.

Creating the workflow and building locally do not prove that GitHub Actions has
passed. The first successful manual run and downloaded-artifact verification
remain post-merge checks for the user.

## Download and verify

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

## Install and remove with adb

Use an Android device with USB debugging enabled and Android SDK Platform Tools
(`adb`) available on your computer. Connect the device and approve the USB
debugging prompt. From the verified bundle directory:

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

## Local build verification

With the toolchain above already available, run these commands individually from
`frontend/`:

```bash
flutter --version
flutter pub get --enforce-lockfile
git diff --exit-code HEAD -- pubspec.lock
dart format --output=none --set-exit-if-changed .
flutter analyze --no-pub
flutter test --no-pub
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
App Links, and iOS/TestFlight are separate work. **Manual mobile E2E is a separate
task**; successful tests and APK assembly do not establish staging E2E results.
