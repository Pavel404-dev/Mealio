"""Offline integration checks with fake gh and adb executables."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INSTALLER = ROOT / "install-android-staging-qa.py"
SHA = "a" * 40
SERIAL = "test-device-123"
REPO = "github.com/Pavel404-dev/Mealio"

FAKE_GH = '''#!/usr/bin/env python3
import hashlib
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
with open(os.environ["CALL_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(["gh", *args]) + "\\n")
if "--repo" not in args or args[args.index("--repo") + 1] != "github.com/Pavel404-dev/Mealio":
    sys.exit(2)
if args[:2] == ["run", "view"]:
    print(json.dumps({
        "workflowName": os.environ.get("WORKFLOW", "Android Staging QA APK"),
        "status": os.environ.get("RUN_STATUS", "completed"),
        "conclusion": os.environ.get("RUN_CONCLUSION", "success"),
        "headBranch": os.environ.get("RUN_BRANCH", "main"),
        "headSha": os.environ.get("RUN_SHA", "a" * 40),
    }))
elif args[:2] == ["run", "download"]:
    directory = Path(args[args.index("--dir") + 1])
    sha = os.environ.get("SOURCE_SHA", "a" * 40)
    apk = b"synthetic APK only for offline tests"
    (directory / "mealio-staging-qa-debug.apk").write_bytes(apk)
    (directory / "SOURCE_COMMIT.txt").write_text(sha + "\\n")
    digest = hashlib.sha256(apk).hexdigest()
    if os.environ.get("BAD_CHECKSUM") == "1":
        digest = "0" * 64
    (directory / "SHA256SUMS").write_text(digest + "  mealio-staging-qa-debug.apk\\n")
else:
    sys.exit(2)
'''

FAKE_ADB = '''#!/usr/bin/env python3
import json
import os
import sys

args = sys.argv[1:]
with open(os.environ["CALL_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps(["adb", *args]) + "\\n")
if args == ["devices"]:
    state = os.environ.get("DEVICE_STATE", "device")
    print("List of devices attached")
    if state != "absent":
        print("test-device-123\\t" + state)
elif args[:3] == ["-s", "test-device-123", "install"]:
    print(os.environ.get("INSTALL_RESULT", "Success"))
else:
    sys.exit(2)
'''


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        for name, content in (("gh", FAKE_GH), ("adb", FAKE_ADB)):
            executable = self.directory / name
            executable.write_text(content)
            executable.chmod(0o755)
        self.log = self.directory / "calls.jsonl"

    def run_installer(self, **settings):
        env = os.environ.copy()
        env.update({"PATH": f"{self.directory}:{env['PATH']}", "CALL_LOG": str(self.log)})
        env.update(settings)
        result = subprocess.run(
            [sys.executable, str(INSTALLER), "12345", SHA, SERIAL],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        return result, calls

    def assert_no_install(self, calls):
        self.assertFalse(any(call[0] == "adb" and "install" in call for call in calls))

    def test_success(self):
        result, calls = self.run_installer(
            GH_HOST="example.invalid", GH_REPO="elsewhere/other"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("APK installed successfully", result.stdout)
        self.assertEqual(calls[0][:4], ["gh", "run", "view", "12345"])
        self.assertEqual(calls[1][0:4], ["gh", "run", "download", "12345"])
        for call in calls[:2]:
            self.assertEqual(call[call.index("--repo") + 1], REPO)
        self.assertEqual(calls[1][calls[1].index("--name") + 1], f"mealio-internal-staging-qa-debug-{SHA}")
        self.assertEqual(calls[2], ["adb", "devices"])
        self.assertEqual(calls[3][:5], ["adb", "-s", SERIAL, "install", "-r"])

    def test_run_sha_mismatch(self):
        result, calls = self.run_installer(RUN_SHA="b" * 40)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("headSha", result.stderr)
        self.assertEqual(len(calls), 1)
        self.assert_no_install(calls)

    def test_source_sha_mismatch(self):
        result, calls = self.run_installer(SOURCE_SHA="b" * 40)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SOURCE_COMMIT.txt", result.stderr)
        self.assert_no_install(calls)

    def test_wrong_workflow_branch_or_result(self):
        for setting in (
            {"WORKFLOW": "Frontend Tests"},
            {"RUN_BRANCH": "feature"},
            {"RUN_STATUS": "in_progress"},
            {"RUN_CONCLUSION": "failure"},
        ):
            with self.subTest(setting=setting):
                self.log.unlink(missing_ok=True)
                result, calls = self.run_installer(**setting)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(calls), 1)
                self.assert_no_install(calls)

    def test_bad_checksum(self):
        result, calls = self.run_installer(BAD_CHECKSUM="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum", result.stderr)
        self.assert_no_install(calls)

    def test_absent_or_unauthorized_device(self):
        for state in ("absent", "unauthorized", "offline"):
            with self.subTest(state=state):
                self.log.unlink(missing_ok=True)
                result, calls = self.run_installer(DEVICE_STATE=state)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(state if state != "absent" else "absent", result.stderr)
                self.assert_no_install(calls)

    def test_adb_failure_output_is_not_reported_as_success(self):
        result, calls = self.run_installer(INSTALL_RESULT="Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE]")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("adb install did not confirm success", result.stderr)
        self.assertEqual(sum("install" in call for call in calls), 1)


if __name__ == "__main__":
    unittest.main()
