"""bin/server orchestration tests. Every external tool is a mock; nothing real runs."""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SERVER = Path(__file__).resolve().parents[1] / "bin/server"
AGE_KEY = "AGE-SECRET-KEY-1TESTONLYNOTAREALKEY"
MOCK = r'''
import json, os, subprocess, sys, time
from pathlib import Path

name = Path(sys.argv[0]).name
args = sys.argv[1:]
flag = lambda key: os.environ.get(key) == "1"
stdin = "" if sys.stdin.isatty() else sys.stdin.read()
with open(os.environ["MOCK_LOG"], "a") as log:
    log.write(json.dumps({"argv": [name, *args], "stdin": stdin}) + "\n")
command = " ".join(args)

def snapshots():
    print(json.dumps([{"id": "abc", "time": os.environ["SNAP_TIME"]}]))

if name == "sops" and args[:1] == ["exec-env"]:
    # Like sops: run the command through a shell with the "decrypted" values.
    secrets = {"TOFU_BACKEND_BUCKET": "state-bucket", "TF_VAR_hcloud_token": "decrypted"}
    sys.exit(subprocess.call(["sh", "-c", args[2]], env=dict(os.environ, **secrets)))
if name == "tofu":
    if "TF_VAR_hcloud_token" not in os.environ:
        sys.exit("tofu ran without the decrypted infra secrets")
    if "state" in args and flag("VPS"):
        print("hcloud_server.minecraft")
    if "output" in args:
        print("192.0.2.1")
elif name == "docker":
    if "ps" in args and flag("LOCAL"):
        print("minecraft-service")
    if "backup now" in command and flag("BACKUP_FAIL"):
        sys.exit(1)
    if "snapshots" in args:
        snapshots()
elif name == "ssh":
    if "date -u +%s" in command:
        print(int(time.time()))
    if "backup now" in command and flag("BACKUP_FAIL"):
        sys.exit(1)
    if "restic snapshots" in command:
        snapshots()
elif name == "git":
    if "rev-parse" in args:
        print("0123456789abcdef0123456789abcdef01234567")
    if args[:1] == ["remote"]:
        print("github")
    if "--contains" in args and not flag("UNPUSHED"):
        print("  github/main")
'''


def iso(offset_seconds):
    """A restic-style timestamp: nanoseconds and a non-UTC offset."""
    zone = timezone(timedelta(hours=1))
    moment = datetime.now(zone) + timedelta(seconds=offset_seconds)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.123456789+01:00")


class ServerTests(unittest.TestCase):
    def run_server(self, *argv, **flags):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "bin").mkdir()
        (root / "infra").mkdir()
        (root / "scripts").mkdir()
        shutil.copy(SERVER, root / "bin/server")
        # Stand-in deploy script: records the settings bin/server hands it.
        (root / "scripts/deploy.sh").write_text(
            'echo "{\\"argv\\": [\\"deploy.sh\\", \\"RESTORE=$RESTORE\\"], '
            '\\"stdin\\": \\"\\"}" >> "$MOCK_LOG"\n')
        mocks = root / "mocks"
        mocks.mkdir()
        for name in ("tofu", "docker", "ssh", "git", "tailscale", "sops", "sleep", "curl"):
            path = mocks / name
            path.write_text(f"#!{sys.executable}\n" + MOCK)
            path.chmod(0o755)
        key = root / "keys.txt"
        key.write_text(f"# created: test\n# public key: age1test\n{AGE_KEY}\n")
        log = root / "calls.jsonl"
        log.touch()
        env = dict(os.environ, MOCK_LOG=str(log), SOPS_AGE_KEY_FILE=str(key),
                   SNAP_TIME=iso(+60), PATH=f"{mocks}:{os.environ['PATH']}")
        for variable in ("TS_HOST", "SSH_USER", "REPO", "RESTORE"):
            env.pop(variable, None)
        env.update({key: value for key, value in flags.items()})
        result = subprocess.run(["bash", str(root / "bin/server"), *argv], env=env,
                                capture_output=True, text=True, stdin=subprocess.DEVNULL)
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        return result, calls

    @staticmethod
    def find(calls, text):
        return [i for i, call in enumerate(calls) if text in " ".join(call["argv"])]

    def test_stop_aborts_when_backup_fails(self):
        for where in ({"LOCAL": "1"}, {"VPS": "1"}):
            with self.subTest(where=where):
                result, calls = self.run_server("stop", BACKUP_FAIL="1", **where)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("still running", result.stderr)
                self.assertFalse(self.find(calls, "compose down"))
                self.assertFalse(self.find(calls, "destroy"))

    def test_stop_aborts_when_snapshot_is_stale(self):
        result, calls = self.run_server("stop", VPS="1", SNAP_TIME=iso(-3600))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no new snapshot", result.stderr)
        self.assertFalse(self.find(calls, "compose down"))
        self.assertFalse(self.find(calls, "destroy"))

    def test_stop_vps_backs_up_then_destroys(self):
        result, calls = self.run_server("stop", VPS="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        backup = self.find(calls, "backup now")[0]
        down = self.find(calls, "compose down")[0]
        logout = self.find(calls, "tailscale logout")[0]
        destroy = self.find(calls, "destroy")[0]
        self.assertLess(backup, down)
        self.assertLess(down, logout)
        self.assertLess(logout, destroy)
        # The tailnet device is removed after the server is gone; a failed
        # API call (the curl mock returns nothing) only warns.
        forget = self.find(calls, "_forget-device mc-prod")[0]
        self.assertLess(destroy, forget)
        self.assertIn("could not remove mc-prod", result.stderr)

    def test_stop_local_keeps_infrastructure(self):
        result, calls = self.run_server("stop", LOCAL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.find(calls, "compose down"))
        self.assertFalse(self.find(calls, "destroy"))
        self.assertFalse(self.find(calls, "ssh"))

    def test_stop_with_nothing_running_is_a_no_op(self):
        result, calls = self.run_server("stop")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Nothing is running", result.stdout)
        self.assertFalse(self.find(calls, "backup now"))

    def test_only_one_location_runs_the_world(self):
        result, calls = self.run_server("start", "vps", LOCAL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.find(calls, "apply"))
        result, calls = self.run_server("start", "local", VPS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.find(calls, "deploy.sh"))

    def test_start_vps_requires_pushed_commit(self):
        result, calls = self.run_server("start", "vps", UNPUSHED="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not pushed", result.stderr)
        self.assertFalse(self.find(calls, "apply"))

    def test_start_vps_sends_age_key_only_on_stdin(self):
        result, calls = self.run_server("start", "vps")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.find(calls, "apply"))
        deploy = calls[self.find(calls, "scripts/deploy.sh")[0]]
        self.assertIn("RESTORE=latest", " ".join(deploy["argv"]))
        self.assertEqual(deploy["stdin"].strip(), AGE_KEY)
        for call in calls:
            self.assertNotIn(AGE_KEY, " ".join(call["argv"]))

    def test_start_local_restores_latest(self):
        result, calls = self.run_server("start", "local")
        self.assertEqual(result.returncode, 0, result.stderr)
        deploy = calls[self.find(calls, "deploy.sh")[0]]["argv"]
        self.assertEqual(deploy, ["deploy.sh", "RESTORE=latest"])

    def test_restart_in_same_place_does_not_restore(self):
        result, calls = self.run_server("start", "local", LOCAL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        deploy = calls[self.find(calls, "deploy.sh")[0]]["argv"]
        self.assertIn("RESTORE=", deploy)

    def test_tofu_gets_secrets_only_through_sops(self):
        result, calls = self.run_server("tofu", "plan")
        self.assertEqual(result.returncode, 0, result.stderr)
        init = next(c["argv"] for c in calls if c["argv"][0] == "tofu" and "init" in c["argv"])
        self.assertIn("-backend-config=bucket=state-bucket", init)
        self.assertTrue(self.find(calls, "plan"))
        for call in calls:
            if call["argv"][0] == "sops":
                self.assertEqual(call["argv"][1:3], ["exec-env", call["argv"][2]])
                self.assertTrue(call["argv"][2].endswith("secrets/infra.enc.env"))

    def test_unknown_command_shows_usage(self):
        result, _ = self.run_server("launch")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("bin/server start local", result.stderr)


if __name__ == "__main__":
    unittest.main()
