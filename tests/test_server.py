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
    if "--tag pre-prune" in command:
        # Pre-prune snapshots: PRE_PRUNE, plus the one `restic tag --add` tagged.
        tagged = json.loads(os.environ.get("PRE_PRUNE", "[]"))
        if Path(os.environ["MOCK_LOG"] + ".tagged").exists():
            tagged.append({"id": "abc", "time": os.environ["SNAP_TIME"]})
        print(json.dumps(tagged))
    else:
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
    if "test -f" in command and not flag("WORLD_ON_VPS"):
        sys.exit(1)
    if "date -u +%s" in command:
        print(int(time.time()))
    if "backup now" in command and flag("BACKUP_FAIL"):
        sys.exit(1)
    if "restic snapshots" in command:
        snapshots()
    if "tag --add pre-prune" in command:
        Path(os.environ["MOCK_LOG"] + ".tagged").touch()
    if "scripts/prune.sh" in command and flag("PRUNE_FAIL"):
        sys.exit(1)
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
        (root / "scripts/prune.sh").write_text(
            'echo "{\\"argv\\": [\\"prune.sh\\", \\"$*\\"], \\"stdin\\": \\"\\"}" >> "$MOCK_LOG"\n')
        (root / "prune").mkdir()
        (root / "prune/settings.env").write_text(
            f"AUTO_PRUNE_DAYS={flags.pop('AUTO_PRUNE_DAYS', '0')}\nPRUNE_KEEP_SNAPSHOTS=2\n")
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
        result, calls = self.run_server("stop", BACKUP_FAIL="1", VPS="1")
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

    def test_stop_local_never_backs_up(self):
        result, calls = self.run_server("stop", LOCAL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.find(calls, "compose down"))
        self.assertFalse(self.find(calls, "backup now"))
        self.assertFalse(self.find(calls, "destroy"))
        self.assertFalse(self.find(calls, "ssh"))
        self.assertIn("nothing is saved to R2", result.stdout)

    def test_only_the_vps_deploy_enables_backups(self):
        _, calls = self.run_server("start", "vps")
        self.assertIn("BACKUPS=1", " ".join(calls[self.find(calls, "scripts/deploy.sh")[0]]["argv"]))
        _, calls = self.run_server("start", "local")
        self.assertFalse(self.find(calls, "BACKUPS=1"))

    def test_backup_checks_only_read_vps_snapshots(self):
        _, calls = self.run_server("stop", VPS="1")
        for i in self.find(calls, "restic snapshots"):
            self.assertIn("--host mc-backup-worker", " ".join(calls[i]["argv"]))

    def test_prune_backs_up_tags_and_restarts_around_the_prune(self):
        result, calls = self.run_server("prune", VPS="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        order = [self.find(calls, text)[0] for text in (
            "backup now", "tag --add pre-prune abc", "compose stop", "scripts/prune.sh", "up -d --wait")]
        self.assertEqual(order, sorted(order))
        self.assertFalse(self.find(calls, "destroy"))

    def test_prune_keeps_only_the_newest_pre_prune_tags(self):
        snaps = json.dumps([{"id": f"s{n}", "time": iso(-86400 * n)} for n in range(4)])
        result, calls = self.run_server("prune", VPS="1", PRE_PRUNE=snaps)
        self.assertEqual(result.returncode, 0, result.stderr)
        untag = " ".join(calls[self.find(calls, "tag --remove pre-prune")[0]]["argv"])
        # PRUNE_KEEP_SNAPSHOTS=2 keeps the new one (abc) and s0.
        self.assertIn("s1 s2 s3", untag)
        self.assertNotIn("s0", untag)
        self.assertIn("rollbacks: abc", result.stdout)

    def test_failed_prune_restarts_the_game(self):
        result, calls = self.run_server("prune", VPS="1", PRUNE_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertLess(self.find(calls, "scripts/prune.sh")[0], self.find(calls, "up -d --wait")[0])

    def test_real_prune_runs_only_on_the_vps(self):
        result, calls = self.run_server("prune", LOCAL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("read-only", result.stderr)
        self.assertFalse(self.find(calls, "prune.sh"))
        result, calls = self.run_server("prune", "--dry-run", LOCAL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.find(calls, "prune.sh --dry-run"))

    def test_stop_prunes_first_only_when_due(self):
        recent = json.dumps([{"id": "p", "time": iso(-86400 * 5)}])
        cases = (({"AUTO_PRUNE_DAYS": "0"}, False),
                 ({"AUTO_PRUNE_DAYS": "30", "PRE_PRUNE": recent}, False),
                 ({"AUTO_PRUNE_DAYS": "3", "PRE_PRUNE": recent}, True),
                 ({"AUTO_PRUNE_DAYS": "30"}, True))  # never pruned
        for flags, due in cases:
            with self.subTest(**flags):
                result, calls = self.run_server("stop", VPS="1", **flags)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(bool(self.find(calls, "scripts/prune.sh")), due)
                if due:
                    self.assertLess(self.find(calls, "scripts/prune.sh")[0],
                                    self.find(calls, "destroy")[0])

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

    def test_existing_vps_restores_only_without_a_world(self):
        for world, expected in (("1", "RESTORE=''"), ("", "RESTORE=latest")):
            with self.subTest(world_on_vps=bool(world)):
                result, calls = self.run_server("start", "vps", VPS="1", WORLD_ON_VPS=world)
                self.assertEqual(result.returncode, 0, result.stderr)
                deploy = calls[self.find(calls, "scripts/deploy.sh")[0]]
                self.assertIn(expected + " ", " ".join(deploy["argv"]) + " ")

    def test_cloud_init_wait_is_a_separate_session(self):
        _, calls = self.run_server("start", "vps")
        wait = self.find(calls, "cloud-init status --wait")[0]
        deploy = self.find(calls, "scripts/deploy.sh")[0]
        self.assertLess(wait, deploy)
        self.assertNotIn("cloud-init", " ".join(calls[deploy]["argv"]))

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
