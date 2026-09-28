"""Signing integration tests: temporary synthetic keys, real JDK/Android tools.

Requires JAVA_HOME and ANDROID_HOME with platform 36 and build-tools 36.0.0.
Only the Flutter build is substituted with a tiny APK to keep these tests fast.
"""

import base64
import contextlib
import hashlib
import importlib.util
import io
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "qa_signing", Path(__file__).with_name("build-android-staging-qa.py")
)
qa = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qa)


class SigningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="mealio-synthetic-signing-")
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.java = Path(os.environ["JAVA_HOME"])
        cls.android = Path(os.environ["ANDROID_HOME"])
        cls.keytool = str(cls.java / "bin/keytool")
        cls.apksigner = str(cls.android / "build-tools/36.0.0/apksigner")
        cls.test_env = {
            **os.environ,
            "ANDROID_QA_STORE_PASSWORD": "synthetic-test-store-only",
            "ANDROID_QA_KEY_PASSWORD": "synthetic-test-key-only",
            "ANDROID_QA_KEY_ALIAS": "synthetic-test-only",
        }
        cls.stores = []
        for index in range(2):
            store = cls.root / f"synthetic-{index}.jks"
            cls.tool(
                [
                    cls.keytool,
                    "-genkeypair",
                    "-keystore",
                    str(store),
                    "-storetype",
                    "JKS",
                    "-storepass:env",
                    "ANDROID_QA_STORE_PASSWORD",
                    "-keypass:env",
                    "ANDROID_QA_KEY_PASSWORD",
                    "-alias",
                    "synthetic-test-only",
                    "-keyalg",
                    "RSA",
                    "-keysize",
                    "2048",
                    "-validity",
                    "1",
                    "-dname",
                    "CN=Synthetic disposable test only",
                    "-noprompt",
                ]
            )
            cls.stores.append(store)
        cert = cls.tool(
            [
                cls.keytool,
                "-exportcert",
                "-keystore",
                str(cls.stores[0]),
                "-storepass:env",
                "ANDROID_QA_STORE_PASSWORD",
                "-alias",
                "synthetic-test-only",
            ]
        )
        cls.digest = hashlib.sha256(cert).hexdigest()
        manifest = cls.root / "AndroidManifest.xml"
        manifest.write_text("""<manifest xmlns:android="http://schemas.android.com/apk/res/android"
            package="invalid.example.synthetic.signingtest" android:versionCode="1">
            <uses-sdk android:minSdkVersion="24" android:targetSdkVersion="36"/>
            <application android:hasCode="false"/>
            </manifest>""")
        cls.unsigned = cls.root / "unsigned.apk"
        cls.tool(
            [
                str(cls.android / "build-tools/36.0.0/aapt2"),
                "link",
                "--manifest",
                str(manifest),
                "-I",
                str(cls.android / "platforms/android-36/android.jar"),
                "-o",
                str(cls.unsigned),
            ]
        )

    @classmethod
    def tool(cls, args, env=None):
        result = subprocess.run(
            args, env=env or cls.test_env, capture_output=True, check=False
        )
        if result.returncode:
            raise AssertionError(f"Synthetic fixture tool failed: {args[0]}")
        return result.stdout

    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=self.root)
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.frontend = self.directory / "frontend"
        self.frontend.mkdir()
        (self.frontend / qa.APK).parent.mkdir(parents=True)
        self.env = {
            **self.test_env,
            "ANDROID_QA_KEYSTORE_BASE64": base64.b64encode(
                self.stores[0].read_bytes()
            ).decode(),
            "ANDROID_QA_CERT_SHA256": self.digest,
            "RUNNER_TEMP": str(self.directory),
        }
        self.build_calls = 0
        self.signer_index = 0
        self.build_error = False
        self.tamper = False
        self.output = io.StringIO()

    def command(self, args, env, cwd, label):
        self.assertNotIn("ANDROID_QA_KEYSTORE_BASE64", env)
        if args[0] != "flutter":
            return qa_command(args, env, cwd, label)
        self.build_calls += 1
        self.assertEqual(env["MEALIO_QA_SIGNING"], "true")
        store = Path(env["MEALIO_QA_KEYSTORE_PATH"])
        self.assertEqual(stat.S_IMODE(store.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(store.parent.stat().st_mode), 0o700)
        self.assertFalse((cwd / qa.APK).exists())
        self.assertEqual(
            args,
            [
                "flutter",
                "build",
                "apk",
                "--debug",
                "--no-pub",
                "--dart-define=API_BASE_URL=https://backend-staging-362e.up.railway.app",
            ],
        )
        if self.build_error:
            raise qa.SigningError("Synthetic build failure")
        # Using a different key simulates Gradle silently falling back to debug signing.
        self.tool(
            [
                self.apksigner,
                "sign",
                "--ks",
                str(self.stores[self.signer_index]),
                "--ks-pass",
                "env:ANDROID_QA_STORE_PASSWORD",
                "--key-pass",
                "env:ANDROID_QA_KEY_PASSWORD",
                "--out",
                str(cwd / qa.APK),
                str(self.unsigned),
            ],
            env,
        )
        if self.tamper:
            (cwd / qa.APK).write_bytes(b"corrupt synthetic APK")
        return b""

    def run_build(self):
        with (
            patch.dict(os.environ, self.env, clear=True),
            patch.object(qa, "command", side_effect=self.command),
            contextlib.redirect_stdout(self.output),
        ):
            try:
                qa.build(self.frontend)
            finally:
                self.assertFalse((self.directory / "mealio-qa-signing").exists())

    def test_two_builds_same_certificate_and_restricted_temporary_file(self):
        for _ in range(2):
            self.run_build()
        self.assertEqual(self.build_calls, 2)
        self.assertEqual(
            self.output.getvalue().count(
                f"Verified APK certificate SHA-256: {self.digest}"
            ),
            2,
        )
        for name in qa.SECRETS:
            self.assertNotIn(self.env[name], self.output.getvalue())

    def test_colon_uppercase_fingerprint(self):
        self.env["ANDROID_QA_CERT_SHA256"] = ":".join(
            self.digest[i : i + 2] for i in range(0, 64, 2)
        ).upper()
        self.run_build()

    def test_missing_settings_fail_before_build(self):
        for name in (*qa.SECRETS, "ANDROID_QA_CERT_SHA256"):
            with self.subTest(name=name):
                original = self.env.pop(name)
                with self.assertRaisesRegex(qa.SigningError, name):
                    self.run_build()
                self.env[name] = original
        self.assertEqual(self.build_calls, 0)

    def test_invalid_base64_or_keystore(self):
        for value in ("not-base64!", base64.b64encode(b"not a keystore").decode()):
            with self.subTest(value=value):
                self.env["ANDROID_QA_KEYSTORE_BASE64"] = value
                with self.assertRaises(qa.SigningError):
                    self.run_build()
        self.assertEqual(self.build_calls, 0)

    def test_wrong_passwords_or_alias(self):
        for name in qa.SECRETS[1:]:
            with self.subTest(name=name):
                original = self.env[name]
                self.env[name] = "synthetic-invalid-value"
                with self.assertRaisesRegex(
                    qa.SigningError, "private key validation failed"
                ) as error:
                    self.run_build()
                self.assertNotIn(self.env[name], str(error.exception))
                self.env[name] = original
        self.assertEqual(self.build_calls, 0)

    def test_wrong_or_malformed_expected_fingerprint(self):
        for value in ("0" * 64, "malformed"):
            with self.subTest(value=value):
                self.env["ANDROID_QA_CERT_SHA256"] = value
                with self.assertRaisesRegex(qa.SigningError, "ANDROID_QA_CERT_SHA256"):
                    self.run_build()
        self.assertEqual(self.build_calls, 0)

    def test_fallback_to_another_key_is_rejected(self):
        self.signer_index = 1
        with self.assertRaisesRegex(qa.SigningError, "APK signer does not match"):
            self.run_build()
        self.assertNotIn("Verified APK", self.output.getvalue())

    def test_invalid_apk_signature_is_rejected(self):
        self.tamper = True
        with self.assertRaisesRegex(
            qa.SigningError, "APK signature verification failed"
        ):
            self.run_build()

    def test_cleanup_on_build_failure(self):
        self.build_error = True
        with self.assertRaisesRegex(qa.SigningError, "Synthetic build failure"):
            self.run_build()

    def test_tool_failure_does_not_expose_output(self):
        with patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(
                [], 1, b"synthetic-private-output", b"synthetic-password-output"
            ),
        ):
            with self.assertRaises(qa.SigningError) as error:
                qa_command(["tool"], {}, self.frontend, "Test validation")
        self.assertNotIn("synthetic-", str(error.exception))

    @unittest.skipUnless(
        os.environ.get("MEALIO_TEST_GRADLE") == "1",
        "set MEALIO_TEST_GRADLE=1 after flutter pub get to check the real Gradle model",
    )
    def test_real_gradle_signing_selection_and_missing_settings(self):
        init = self.directory / "check-signing.gradle"
        init.write_text("""gradle.projectsEvaluated {
            def app = gradle.rootProject.findProject(':app')
            if (app == null) return
            app.tasks.register('checkQaSigningModel') {
                doLast {
                    def android = app.extensions.getByName('android')
                    def expected = System.getenv('MEALIO_QA_SIGNING') == 'true' ? 'stagingQa' : 'debug'
                    assert android.buildTypes.debug.signingConfig.name == expected
                    assert android.buildTypes.release.signingConfig.name == 'debug'
                    assert android.defaultConfig.applicationId == 'com.mealio.app'
                    if (expected == 'stagingQa') {
                        assert android.buildTypes.debug.signingConfig.storeFile ==
                            new File(System.getenv('MEALIO_QA_KEYSTORE_PATH'))
                    } else {
                        assert android.signingConfigs.findByName('stagingQa') == null
                    }
                }
            }
        }""")
        env = {
            key: value
            for key, value in self.env.items()
            if key not in qa.SECRETS and not key.startswith("MEALIO_QA_")
        }
        args = [
            str(qa.FRONTEND / "android/gradlew"),
            "--console=plain",
            "-I",
            str(init),
            ":app:checkQaSigningModel",
        ]

        def gradle(settings):
            return subprocess.run(
                args,
                env=settings,
                cwd=qa.FRONTEND / "android",
                capture_output=True,
                check=False,
            )

        result = gradle(env)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        env.update({name: self.env[name] for name in qa.SECRETS[1:]})
        env.update(
            MEALIO_QA_SIGNING="true", MEALIO_QA_KEYSTORE_PATH=str(self.stores[0])
        )
        result = gradle(env)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        for name in ("MEALIO_QA_KEYSTORE_PATH", *qa.SECRETS[1:]):
            with self.subTest(missing=name):
                result = gradle(
                    {key: value for key, value in env.items() if key != name}
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    f"Missing required QA signing setting: {name}".encode(),
                    result.stderr,
                )


qa_command = qa.command

if __name__ == "__main__":
    unittest.main()
