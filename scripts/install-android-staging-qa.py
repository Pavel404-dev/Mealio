#!/usr/bin/env python3
"""Install a verified APK from one explicitly selected Android staging QA run."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

WORKFLOW = "Android Staging QA APK"
REPO = "Pavel404-dev/Mealio"
APK = "mealio-staging-qa-debug.apk"
SHA_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
SERIAL_PATTERN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._:-]*\Z")


class InstallError(Exception):
    """An expected validation or command failure."""


def command(*args: str) -> str:
    try:
        result = subprocess.run(args, check=True, text=True, capture_output=True)
    except FileNotFoundError as error:
        raise InstallError(f"Required command is unavailable: {args[0]}") from error
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or error.stdout.strip() or "no details"
        raise InstallError(f"{' '.join(args[:2])} failed: {detail}") from error
    return result.stdout


def regular_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def verify_bundle(directory: Path, sha: str) -> Path:
    expected = {APK, "SOURCE_COMMIT.txt", "SHA256SUMS"}
    if {path.name for path in directory.iterdir()} != expected:
        raise InstallError("Artifact must contain exactly the APK, SOURCE_COMMIT.txt, and SHA256SUMS.")
    if any(not regular_file(directory / name) for name in expected):
        raise InstallError("Artifact files must be regular files, not links or directories.")
    try:
        source = (directory / "SOURCE_COMMIT.txt").read_text(encoding="ascii")
        sums = (directory / "SHA256SUMS").read_text(encoding="ascii")
    except (OSError, UnicodeError) as error:
        raise InstallError("Cannot read artifact metadata files.") from error
    if source != f"{sha}\n":
        raise InstallError("SOURCE_COMMIT.txt does not match the expected commit SHA.")
    match = re.fullmatch(rf"([0-9a-f]{{64}})  {re.escape(APK)}\n", sums)
    if match is None:
        raise InstallError("SHA256SUMS must contain exactly one checksum for the QA APK.")
    apk = directory / APK
    with apk.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != match.group(1):
        raise InstallError("APK SHA-256 checksum does not match SHA256SUMS.")
    return apk


def verify_device(serial: str) -> None:
    output = command("adb", "devices")
    matches = [line.split() for line in output.splitlines()[1:] if line.split()[:1] == [serial]]
    if len(matches) != 1 or len(matches[0]) < 2 or matches[0][1] != "device":
        raise InstallError(f"Android device {serial!r} is absent, offline, or unauthorized.")


def install(run_id: str, sha: str, serial: str) -> None:
    try:
        run = json.loads(command("gh", "run", "view", run_id, "--repo", REPO, "--json", "workflowName,status,conclusion,headBranch,headSha"))
    except (ValueError, TypeError) as error:
        raise InstallError("GitHub returned invalid run metadata.") from error
    if not isinstance(run, dict) or run.get("workflowName") != WORKFLOW:
        raise InstallError(f"Run {run_id} is not an {WORKFLOW} run.")
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        raise InstallError(f"Run {run_id} has not completed successfully.")
    if run.get("headBranch") != "main":
        raise InstallError(f"Run {run_id} was not started for main.")
    if run.get("headSha") != sha:
        raise InstallError("Run headSha does not match the expected commit SHA.")

    artifact = f"mealio-internal-staging-qa-debug-{sha}"
    with tempfile.TemporaryDirectory(prefix="mealio-qa-") as temp:
        directory = Path(temp)
        command("gh", "run", "download", run_id, "--repo", REPO, "--name", artifact, "--dir", str(directory))
        apk = verify_bundle(directory, sha)
        verify_device(serial)
        print(f"Installing verified APK from run {run_id}, commit {sha}, on {serial}.", flush=True)
        result = command("adb", "-s", serial, "install", "-r", str(apk))
        if not result.splitlines() or result.splitlines()[-1].strip() != "Success":
            raise InstallError(f"adb install did not confirm success: {result.strip() or 'no output'}")
        print("APK installed successfully.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id", help="specific GitHub Actions run ID")
    parser.add_argument("sha", help="expected full lowercase 40-character source commit SHA")
    parser.add_argument("serial", help="specific Android device serial")
    args = parser.parse_args()
    if not re.fullmatch(r"[1-9][0-9]*", args.run_id):
        parser.error("run_id must be a positive decimal GitHub Actions run ID")
    if not SHA_PATTERN.fullmatch(args.sha):
        parser.error("sha must be the full lowercase 40-character commit SHA")
    if not SERIAL_PATTERN.fullmatch(args.serial):
        parser.error("serial must be a nonempty Android device serial without whitespace")
    try:
        install(args.run_id, args.sha, args.serial)
    except (InstallError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
