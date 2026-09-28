# Android staging QA APK

[Android Staging QA APK](../.github/workflows/android-staging-qa.yml) builds an
**internal debug QA APK** for the staging backend at
`https://backend-staging-362e.up.railway.app`. `AppConfig` adds `/api/v1` to this
origin. The URL is public configuration; it is the only `dart-define`. Never
put credentials, tokens, SMTP settings, or OpenAI keys in build defines.
Use disposable synthetic QA accounts and data.

## Build contract

The workflow runs automatically when a push to `main` changes `frontend/**`,
the QA build helper or its signing tests, or this workflow file, including
matching PR merges. `workflow_dispatch` allows a manual build **on main only**;
the job skips all other refs and events. PR workflows never receive the QA key.
Backend-only changes do not trigger another APK build.
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
the debug APK is built. The bundle is uploaded only after its signing certificate
matches the configured fingerprint and its APK checksum passes verification.
The upload allowlist contains exactly these three files:

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
APKs**. The QA signing certificate is stable; archive timestamps, the runner
image, JDK patch versions, and Actions major-version tags can change between runs. The checksum
identifies the APK from one particular run; it does not establish reproducibility
across separate builds.

## One-time signing setup by the owner, before merge

Configure these repository **Settings → Secrets and variables → Actions** entries
before merging the signing change. Only the owner generates and backs up the
real key; do not send keys, passwords, or base64 data in chat, issues, or PRs.

| Kind | Exact name | Value |
| --- | --- | --- |
| Secret | `ANDROID_QA_KEYSTORE_BASE64` | Single-line base64 of the dedicated JKS keystore |
| Secret | `ANDROID_QA_STORE_PASSWORD` | Keystore password |
| Secret | `ANDROID_QA_KEY_ALIAS` | Private key alias, e.g. `mealio-staging-qa` |
| Secret | `ANDROID_QA_KEY_PASSWORD` | Private key password |
| Variable | `ANDROID_QA_CERT_SHA256` | Public certificate SHA-256, 64 hex digits or 32 colon-separated hex pairs |

On a trusted owner-controlled computer with JDK 17+, create a private directory
**outside the repository**, preferably on an encrypted volume. Run the following
once in that directory, with terminal recording and shell tracing disabled:

```bash
umask 077
keytool -genkeypair -keystore mealio-staging-qa.jks -storetype JKS \
  -alias mealio-staging-qa -keyalg RSA -keysize 3072 -validity 10000
```

Use the interactive password prompts, a password manager, and strong unique
passwords. The private key password can differ from the store password; enter
the actual chosen value for each secret. Certificate identity fields are public:
use a QA project identity without personal details. Do not reuse a release key,
a local debug key, or a synthetic test key. Do not overwrite an existing QA key.

Get the **public** certificate fingerprint (the password is prompted):

```bash
keytool -list -v -keystore mealio-staging-qa.jks -storetype JKS \
  -alias mealio-staging-qa
```

Copy only the certificate's `SHA256` value to `ANDROID_QA_CERT_SHA256`, not the
SHA-256 checksum of the keystore file. Base64 is encoding, not encryption.
For example, on Linux the owner can upload the keystore directly without
printing it or creating a base64 file:

```bash
base64 -w 0 mealio-staging-qa.jks | gh secret set ANDROID_QA_KEYSTORE_BASE64 \
  --repo github.com/Pavel404-dev/Mealio
```

Set the other secrets through the Actions settings UI or `gh secret set NAME`
using its hidden interactive prompt, never literal passwords in command-line
arguments. Set the public variable in the UI. These are owner instructions;
repository automation does not create the secrets.

Keep encrypted offline backups of the keystore and recoverable password-manager
records for both passwords and the alias. Record the public fingerprint alongside
the backup, and test that a restored copy yields the same fingerprint. GitHub
Secrets is not a downloadable backup. Restrict repository write access and
review changes to the signing workflow and helper before merging.

The helper writes the JKS only to `$RUNNER_TEMP/mealio-qa-signing/qa.jks`
(directory `0700`, file `0600`). It checks all settings, validates the private
key/password with `keytool`, and checks the exported certificate before invoking
Flutter. Gradle selects the separate `stagingQa` config only with
`MEALIO_QA_SIGNING=true`; incomplete QA settings fail instead of selecting the
default debug config. The keystore is removed after the build, including failures;
an `always()` workflow step also removes it on failure/cancellation.

The helper then runs [`apksigner verify --print-certs`](https://developer.android.com/tools/apksigner)
on the actual APK, requires exactly one matching signer, and logs
`Verified APK certificate SHA-256: <public fingerprint>`. A bad key, password,
alias, fingerprint, APK signature, or accidental default debug signer stops
the job before packaging/upload. Tool output from key-bearing commands is
withheld, including failures, to avoid exposing signing inputs in diagnostics.
For a generic build failure, reproduce with a disposable synthetic key locally;
do not enable shell tracing, Gradle debug logs, or upload private diagnostics.

`MEALIO_QA_KEYSTORE_PATH` and `MEALIO_QA_SIGNING` are internal helper-to-Gradle
environment settings, not GitHub Secrets or Dart defines. The default
`~/.android/debug.keystore`, application ID, and release signing stay unchanged.

### Key loss or rotation

Restore the same keystore from backup if possible. Replacing the key changes the
certificate and requires another explicitly approved uninstall/reinstall on QA
devices, with local data loss. Update the keystore, passwords, alias, and expected
fingerprint together; mismatched settings deliberately block builds. Do not
rotate routinely or regenerate the key per run. This workflow does not implement
Android signing lineage or a production key rotation process.

## Build after merging frontend changes

After a matching merge into `main`, open the repository's **Actions** tab and
select **Android Staging QA APK**. Open the run for that merge and confirm its
full commit SHA is the revision intended for QA. Wait for formatting, analysis,
tests, APK build, certificate verification, checksum verification, and upload to
succeed. If a step fails, inspect its logs; do not substitute an artifact from
another run.

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

Android debug signing is for internal testing. Successive CI QA builds now use
the same dedicated certificate. Older CI APKs and ordinary local debug builds
can have a different certificate. The **first transition** to the stable QA
certificate can fail with `INSTALL_FAILED_UPDATE_INCOMPATIBLE`; `install -r`
cannot bypass that mismatch. Plan one uninstall/reinstall on a disposable QA
device. Subsequent stable-key QA APKs can update through `install -r` without
clearing local data. The installer never uninstalls automatically.

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

## Acceptance check after secrets are configured and the change is merged

1. Build run A on `main`. Record its run ID, source SHA and the public fingerprint
   from the successful signing-verification log. Install its verified bundle,
   performing the one-time transition above only if needed and acceptable.
2. Select an explicit app language different from the phone's default. Close and
   reopen the app to confirm the language setting was persisted locally.
3. Start a separate run B on `main` (manual dispatch is sufficient, even for the
   same source SHA). Check that its verification log reports exactly the same
   fingerprint as run A and the configured variable. These must be distinct CI
   runs on fresh runners, not two downloads of the same artifact.
4. Use the installer with **run B's** ID, SHA, and the same device serial. Confirm
   `adb install -r` succeeds without uninstalling or clearing data. Reopen the app
   and confirm the explicit language setting remains. Record both run IDs,
   fingerprints, the update result, and the setting before/after.

The installer still validates exactly three bundle files, SHA, checksum, and run
status. The certificate gate is in CI; the installer does not independently pin
a certificate. For an independent public check on either downloaded APK, run
`apksigner verify --print-certs mealio-staging-qa-debug.apk` and compare its
certificate SHA-256 with the configured variable. An APK file checksum will
usually differ between builds and is not the certificate fingerprint.

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

Run signing and installer tests from the repository root with Python 3.11+,
`JAVA_HOME` pointing to a JDK and `ANDROID_HOME` to an SDK containing platform 36
and Build Tools 36.0.0:

```bash
python3 -m unittest discover -s scripts -p 'test_*.py' -v
```

The signing tests create and remove temporary synthetic keys and tiny APKs.
They use real `keytool`/`apksigner`, cover two signatures with the same key,
missing/invalid inputs, a different signer (silent fallback), corrupt APKs,
restricted permissions, cleanup, and safe failure logs. They substitute the
Flutter build and therefore do not prove device update behavior. After
`flutter pub get`, set `MEALIO_TEST_GRADLE=1` for the same test command to also
check the real Gradle model: ordinary debug without secrets, QA debug, unchanged
release signing/application ID, and missing QA settings. This needs the full
Android toolchain listed above and Gradle dependencies. PR CI enables this check
without any QA secrets. Never use the project's real QA key for local tests.

For an optional local APK build after that verification, run from `frontend/`:

```bash
flutter --version
flutter build apk --debug --no-pub \
  --dart-define=API_BASE_URL=https://backend-staging-362e.up.railway.app
```

Leave `MEALIO_QA_SIGNING` unset for this ordinary local build; it needs no QA
secrets and uses the local debug key. The APK is written to
`frontend/build/app/outputs/flutter-apk/app-debug.apk`.
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
