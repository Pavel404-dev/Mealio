#!/usr/bin/env python3
"""Build the CI-only QA APK, failing closed and logging only public signing data."""

import base64
import binascii
import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
APK = Path("build/app/outputs/flutter-apk/app-debug.apk")
SECRETS = (
    "ANDROID_QA_KEYSTORE_BASE64",
    "ANDROID_QA_STORE_PASSWORD",
    "ANDROID_QA_KEY_ALIAS",
    "ANDROID_QA_KEY_PASSWORD",
)


class SigningError(Exception):
    """A safe diagnostic that never contains secret values or tool output."""


def fingerprint(value: str) -> str:
    value = value.strip()
    if not re.fullmatch(
        r"(?:[0-9a-fA-F]{64}|(?:[0-9a-fA-F]{2}:){31}[0-9a-fA-F]{2})", value
    ):
        raise SigningError(
            "ANDROID_QA_CERT_SHA256 must be a SHA-256 certificate fingerprint."
        )
    return value.replace(":", "").lower()


def command(args: list[str], env: dict[str, str], cwd: Path, label: str) -> bytes:
    # Do not forward arbitrary keytool/Gradle output: even failure diagnostics can
    # contain signing inputs. No passwords are passed in command-line arguments.
    try:
        result = subprocess.run(
            args, env=env, cwd=cwd, capture_output=True, check=False
        )
    except OSError:
        raise SigningError(f"{label}: required tool could not start.") from None
    if result.returncode:
        raise SigningError(
            f"{label} failed; tool output withheld to protect signing material."
        )
    return result.stdout


def build(frontend: Path = FRONTEND) -> None:
    env = os.environ.copy()
    for name in (
        *SECRETS,
        "ANDROID_QA_CERT_SHA256",
        "RUNNER_TEMP",
        "JAVA_HOME",
        "ANDROID_HOME",
    ):
        if not env.get(name):
            raise SigningError(f"Missing required setting: {name}")
    expected = fingerprint(env["ANDROID_QA_CERT_SHA256"])
    env["PATH"] = str(Path(env["JAVA_HOME"]) / "bin") + os.pathsep + env.get("PATH", "")
    try:
        keystore = base64.b64decode(
            env.pop("ANDROID_QA_KEYSTORE_BASE64"), validate=True
        )
    except (ValueError, binascii.Error):
        raise SigningError("ANDROID_QA_KEYSTORE_BASE64 is not valid base64.") from None
    if not keystore:
        raise SigningError("QA keystore is empty.")

    directory = Path(env["RUNNER_TEMP"]) / "mealio-qa-signing"
    # Refuse to reuse an existing directory or symlink. Files never enter the repo.
    directory.mkdir(mode=0o700)
    try:
        store = directory / "qa.jks"
        with store.open("xb") as stream:
            store.chmod(0o600)
            stream.write(keystore)
        keytool = str(Path(env["JAVA_HOME"]) / "bin/keytool")
        common = [
            "-keystore",
            str(store),
            "-storetype",
            "JKS",
            "-storepass:env",
            "ANDROID_QA_STORE_PASSWORD",
            "-alias",
            env["ANDROID_QA_KEY_ALIAS"],
        ]
        # A certificate export alone would not validate the private-key password.
        command(
            [keytool, "-certreq", *common, "-keypass:env", "ANDROID_QA_KEY_PASSWORD"],
            env,
            frontend,
            "QA private key validation",
        )
        certificate = command(
            [keytool, "-exportcert", *common], env, frontend, "QA certificate export"
        )
        if hashlib.sha256(certificate).hexdigest() != expected:
            raise SigningError(
                "QA keystore certificate does not match ANDROID_QA_CERT_SHA256."
            )

        env["MEALIO_QA_SIGNING"] = "true"
        env["MEALIO_QA_KEYSTORE_PATH"] = str(store)
        # Do not reuse an APK left by an earlier build if a tool exits without output.
        (frontend / APK).unlink(missing_ok=True)
        print("QA signing inputs validated; building debug APK.", flush=True)
        command(
            [
                "flutter",
                "build",
                "apk",
                "--debug",
                "--no-pub",
                "--dart-define=API_BASE_URL=https://backend-staging-362e.up.railway.app",
            ],
            env,
            frontend,
            "QA Flutter build",
        )
    finally:
        shutil.rmtree(directory)

    # The key is already deleted; verification only needs the public certificate.
    public_env = {
        key: value
        for key, value in env.items()
        if key not in SECRETS and not key.startswith("MEALIO_QA_")
    }
    apksigner = str(Path(env["ANDROID_HOME"]) / "build-tools/36.0.0/apksigner")
    output = command(
        [apksigner, "verify", "--print-certs", str(frontend / APK)],
        public_env,
        frontend,
        "APK signature verification",
    ).decode("utf-8")
    signers = re.findall(
        r"^Signer #\d+ certificate SHA-256 digest: ([0-9a-fA-F]{64})$",
        output,
        re.MULTILINE,
    )
    if len(signers) != 1 or signers[0].lower() != expected:
        raise SigningError(
            "APK signer does not match ANDROID_QA_CERT_SHA256 (exactly one required)."
        )
    print(f"Verified APK certificate SHA-256: {expected}", flush=True)


def main() -> int:
    try:
        build()
    except SigningError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except (OSError, UnicodeError):
        print(
            "Error: QA signing file or tool output could not be processed.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
