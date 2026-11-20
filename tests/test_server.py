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
    for tag, variable in (("pre-prune", "PRE_PRUNE"), ("pre-restore", "PRE_RESTORE")):
        if f"--tag {tag}" in command:
            # Tagged snapshots: $variable, plus the one `restic tag --add` tagged.
            tagged = json.loads(os.environ.get(variable, "[]"))
            if Path(os.environ["MOCK_LOG"] + ".tagged-" + tag).exists():
                tagged.append({"id": "abc", "time": os.environ["SNAP_TIME"]})
            print(json.dumps(tagged))
            return
    else:
        print(os.environ.get("SNAP_JSON") or json.dumps([{"id": "abc", "time": os.environ["SNAP_TIME"]}]))

if name == "sops" and args[:1] == ["exec-env"]:
    # Like sops: run the command through a shell with the "decrypted" values.
    secrets = {"TOFU_BACKEND_BUCKET": "state-bucket", "TF_VAR_hcloud_token": "decrypted"}
    if args[1].endswith("app.enc.env"):
        secrets.update(R2_ENDPOINT="https://r2.invalid", R2_BUCKET_NAME="backups",
                       R2_ACCESS_KEY_ID="r2-id", R2_SECRET_ACCESS_KEY="r2-secret",
                       RESTIC_PASSWORD="restic-secret")
    else:
        secrets.update(VAULT_ACCESS_KEY_ID="vault-id", VAULT_SECRET_ACCESS_KEY="vault-secret")
    sys.exit(subprocess.call(["sh", "-c", args[2]], env=dict(os.environ, **secrets)))
if name == "tofu":
    if "TF_VAR_hcloud_token" not in os.environ:
        sys.exit("tofu ran without the decrypted infra secrets")
    if "state" in args and os.environ.get("STATE") == "missing":
        sys.exit("Error: No state file was found")
    if "state" in args and os.environ.get("STATE") == "broken":
        sys.exit("Error: AccessDenied")
    if "state" in args and flag("VPS"):
        print("hcloud_server.minecraft")
    if "output" in args:
        print("192.0.2.1")
elif name == "docker":
    if "--entrypoint" in args:  # lib.sh restic(): record where it reads from
        with open(os.environ["MOCK_LOG"] + ".repos", "a") as repos:
            repos.write(f"{os.environ['RESTIC_REPOSITORY']} {os.environ['AWS_ACCESS_KEY_ID']}\n")
        if " check " in f" {command} " and flag("CHECK_FAIL"):
            sys.exit(1)
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
    if "restic" in command and " snapshots " in command + " ":
        snapshots()
    for tag in ("pre-prune", "pre-restore"):
        if f"tag --add {tag}" in command:
            Path(os.environ["MOCK_LOG"] + ".tagged-" + tag).touch()
    if "scripts/restore.sh" in command and flag("RESTORE_FAIL"):
        sys.exit(1)
    if "restic" in command and " check " in command and flag("CHECK_FAIL"):
        print("Fatal: repository contains errors")
        sys.exit(1)
    if "publish-world.sh" in command and flag("PUBLISH_FAIL"):
        sys.exit(1)
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
        for script in ("lib.sh", "snapshots.py", "regions.py", "test-backup.sh"):
            shutil.copy(SERVER.parents[1] / "scripts" / script, root / "scripts" / script)
        # Stand-in deploy script: records the settings bin/server hands it.
        (root / "scripts/deploy.sh").write_text(
            'echo "{\\"argv\\": [\\"deploy.sh\\", \\"RESTORE=$RESTORE\\"], '
            '\\"stdin\\": \\"\\", \\"source\\": \\"${RESTIC_SOURCE:-}\\", '
            '\\"backups\\": \\"${BACKUPS:-}\\"}" >> "$MOCK_LOG"\n'
            '[ "${DEPLOY_FAIL:-}" = 1 ] && exit 1\n'
            'mkdir -p data/minecraft/world && touch data/minecraft/world/level.dat\n')
        mocks = root / "mocks"
        mocks.mkdir()
        for name in ("tofu", "docker", "ssh", "git", "tailscale", "sops", "sleep", "curl", "rclone"):
            path = mocks / name
            path.write_text(f"#!{sys.executable}\n" + MOCK)
            path.chmod(0o755)
        key = root / "keys.txt"
        key.write_text(f"# created: test\n# public key: age1test\n{AGE_KEY}\n")
        log = root / "calls.jsonl"
        log.touch()
        env = dict(os.environ, MOCK_LOG=str(log), SOPS_AGE_KEY_FILE=str(key),
                   SNAP_TIME=iso(+60), PATH=f"{mocks}:{os.environ['PATH']}")
        for variable in ("TS_HOST", "SSH_USER", "REPO", "RESTORE", "BACKUP_PING_URL", "HEALTHCHECKS_API_KEY",
                         "RESTIC_SOURCE", "VAULT_BUCKET", "R2_ENDPOINT"):
            env.pop(variable, None)
        env.update({key: value for key, value in flags.items()})
        result = subprocess.run(["bash", str(root / "bin/server"), *argv], env=env,
                                capture_output=True, text=True, stdin=subprocess.DEVNULL)
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        repos = Path(f"{log}.repos")
        self.repos = repos.read_text().splitlines() if repos.exists() else []
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

    def test_restic_errors_are_not_tracebacks(self):
        result, _ = self.run_server("status", VPS="1", SNAP_JSON="not json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Latest backup: unknown", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_stop_keeps_the_vps_when_the_integrity_check_fails(self):
        result, calls = self.run_server("stop", VPS="1", CHECK_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("integrity check", result.stderr)
        self.assertLess(self.find(calls, "backup now")[0], self.find(calls, "check --read-data-subset")[0])
        self.assertFalse(self.find(calls, "compose down"))
        self.assertFalse(self.find(calls, "destroy"))

    def test_stop_copies_the_backups_into_the_vault_after_destroy(self):
        result, calls = self.run_server("stop", VPS="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        vault = self.find(calls, "_vault-copy")[0]
        self.assertLess(self.find(calls, "destroy")[0], vault)
        # The vault key is only decrypted on the laptop, never sent to the VPS.
        for call in calls:
            if call["argv"][0] == "ssh":
                self.assertNotIn("VAULT", " ".join(call["argv"]) + call["stdin"])

    def test_stop_pauses_the_alert_check_after_destroy(self):
        result, calls = self.run_server("stop", VPS="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(self.find(calls, "destroy")[0], self.find(calls, "_pause-alerts")[0])

    def test_pause_alerts_keeps_the_api_key_out_of_argv(self):
        url = "https://hc-ping.com/0f75a81d-70e5-43c5-b892-f33c524284f2"
        result, calls = self.run_server("_pause-alerts", BACKUP_PING_URL=url,
                                        HEALTHCHECKS_API_KEY="hcw_secretkey")
        self.assertEqual(result.returncode, 0, result.stderr)
        curl = calls[self.find(calls, "api/v3/checks/0f75a81d-70e5-43c5-b892-f33c524284f2/pause")[0]]
        self.assertNotIn("hcw_secretkey", " ".join(curl["argv"]))
        self.assertIn("X-Api-Key: hcw_secretkey", curl["stdin"])
        # Unconfigured: nothing happens.
        result, calls = self.run_server("_pause-alerts")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.find(calls, "healthchecks.io"))

    def test_vault_copy_runs_under_both_secret_files(self):
        _, calls = self.run_server("vault")
        files = [Path(call["argv"][2]).name for call in calls if call["argv"][0] == "sops"]
        self.assertEqual(files, ["app.enc.env", "infra.enc.env"])
        self.assertIn("_vault-copy", [c for c in calls if c["argv"][0] == "sops"][-1]["argv"][3])
        # rclone reads the backups bucket and writes the vault, keys by environment only.
        rclone = calls[self.find(calls, "rclone copy")[0]]["argv"]
        self.assertEqual(rclone[2:4], ["backups:backups", "vault:cactuz-mc-vault"])
        self.assertNotIn("vault-secret", " ".join(rclone))

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

    def test_stop_publishes_the_world_after_down_and_before_destroy(self):
        result, calls = self.run_server("stop", VPS="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        publish = self.find(calls, "publish-world.sh")[0]
        self.assertLess(self.find(calls, "compose down")[0], publish)
        self.assertLess(publish, self.find(calls, "destroy")[0])
        # A failed publish only warns; the VPS is still deleted.
        result, calls = self.run_server("stop", VPS="1", PUBLISH_FAIL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("could not publish world.zip", result.stderr)
        self.assertTrue(self.find(calls, "destroy"))

    def test_stop_local_never_backs_up(self):
        result, calls = self.run_server("stop", LOCAL="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.find(calls, "compose down"))
        self.assertFalse(self.find(calls, "backup now"))
        self.assertFalse(self.find(calls, "destroy"))
        self.assertFalse(self.find(calls, "ssh"))
        self.assertFalse(self.find(calls, "publish-world"))
        self.assertIn("nothing is saved to R2", result.stdout)

    def test_only_the_vps_deploy_enables_backups(self):
        _, calls = self.run_server("start", "vps")
        self.assertIn("BACKUPS=1", " ".join(calls[self.find(calls, "scripts/deploy.sh")[0]]["argv"]))
        _, calls = self.run_server("start", "local")
        self.assertFalse(self.find(calls, "BACKUPS=1"))

    def test_backup_checks_only_read_vps_snapshots(self):
        _, calls = self.run_server("stop", VPS="1")
        checks = [i for i in self.find(calls, "snapshots") if calls[i]["argv"][0] != "rclone"]
        self.assertTrue(checks)
        for i in checks:
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

    def test_missing_state_means_no_vps_but_a_broken_read_stops(self):
        result, _ = self.run_server("status", STATE="missing")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Stopped", result.stdout)
        result, _ = self.run_server("status", STATE="broken")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("could not read the OpenTofu state", result.stderr)

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

    # --- Backups from the laptop (read-only) ---------------------------------

    SECRET_VALUES = ("r2-secret", "restic-secret", "vault-secret", "decrypted")

    def assert_no_secrets_in_argv(self, calls):
        for call in calls:
            for value in self.SECRET_VALUES:
                self.assertNotIn(value, " ".join(call["argv"]))

    def assert_laptop_only(self, calls):
        """Read-only from the laptop: no VPS, no OpenTofu, nothing that writes."""
        for text in ("ssh", "apply", "destroy", "backup now", "tag --add", "rclone", "deploy.sh"):
            self.assertFalse(self.find(calls, text), text)

    def test_backups_lists_vps_snapshots_without_a_lock(self):
        result, calls = self.run_server("backups")
        self.assertEqual(result.returncode, 0, result.stderr)
        listing = " ".join(calls[self.find(calls, "--entrypoint restic")[0]]["argv"])
        self.assertIn("--no-lock snapshots --host mc-backup-worker --compact", listing)
        self.assertEqual(self.repos, ["s3:https://r2.invalid/backups r2-id"])
        self.assertEqual([Path(c["argv"][2]).name for c in calls if c["argv"][0] == "sops"], ["app.enc.env"])
        self.assert_laptop_only(calls)
        self.assert_no_secrets_in_argv(calls)

    def test_backups_vault_reads_the_vault_with_its_keys(self):
        result, calls = self.run_server("backups", "--vault")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("the vault (cactuz-mc-vault)", result.stdout)
        self.assertEqual(self.repos, ["s3:https://r2.invalid/cactuz-mc-vault vault-id"])
        self.assert_laptop_only(calls)
        self.assert_no_secrets_in_argv(calls)
        result, _ = self.run_server("backups", "--bogus")
        self.assertNotEqual(result.returncode, 0)

    def test_check_reads_a_share_of_the_data_without_writing(self):
        for argv, percent in ((("check",), "5%"), (("check", "25"), "25%"), (("check", "2.5"), "2.5%")):
            with self.subTest(argv=argv):
                result, calls = self.run_server(*argv)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Backup check passed", result.stdout)
                check = " ".join(calls[self.find(calls, " check ")[0]]["argv"])
                self.assertIn(f"--no-lock check --read-data-subset {percent}", check)
                for i in self.find(calls, "--entrypoint restic"):
                    self.assertIn("--no-lock", calls[i]["argv"])
                self.assert_laptop_only(calls)
                self.assert_no_secrets_in_argv(calls)

    def test_check_vault_and_failures(self):
        result, calls = self.run_server("check", "10", "--vault")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.repos)
        self.assertEqual(set(self.repos), {"s3:https://r2.invalid/cactuz-mc-vault vault-id"})
        result, _ = self.run_server("check", CHECK_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Backup check passed", result.stdout)
        for bad in ("abc", "0", "150", "5%"):
            with self.subTest(percent=bad):
                result, calls = self.run_server("check", bad)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.find(calls, " check "))

    def test_drill_restores_from_the_vault_checks_and_stops(self):
        result, calls = self.run_server("drill")
        self.assertEqual(result.returncode, 0, result.stderr)
        deploy = calls[self.find(calls, "deploy.sh")[0]]
        self.assertEqual(deploy["argv"], ["deploy.sh", "RESTORE=latest"])
        self.assertEqual((deploy["source"], deploy["backups"]), ("vault", ""))
        self.assertLess(self.find(calls, "deploy.sh")[0], self.find(calls, "compose down")[0])
        self.assertIn("Drill passed", result.stdout)
        self.assert_no_secrets_in_argv(calls)
        for text in ("ssh", "apply", "destroy", "backup now", "rclone"):
            self.assertFalse(self.find(calls, text), text)
        _, calls = self.run_server("drill", "abc123")
        self.assertEqual(calls[self.find(calls, "deploy.sh")[0]]["argv"], ["deploy.sh", "RESTORE=abc123"])

    def test_drill_failure_stops_the_copy_and_fails(self):
        result, calls = self.run_server("drill", DEPLOY_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("drill failed", result.stderr)
        self.assertTrue(self.find(calls, "compose down"))
        result, calls = self.run_server("drill", LOCAL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.find(calls, "deploy.sh"))
        result, calls = self.run_server("drill", "../etc")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.find(calls, "deploy.sh"))

    # --- Restores ------------------------------------------------------------

    def test_restore_on_the_vps_takes_a_safety_backup_first(self):
        result, calls = self.run_server("restore", "ab", "--yes", VPS="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        order = [self.find(calls, text)[0] for text in (
            "--json --host mc-backup-worker",  # the ID is resolved among VPS snapshots
            "backup now", "tag --add pre-restore abc", "scripts/restore.sh world abc --yes")]
        self.assertEqual(order, sorted(order))
        run = " ".join(calls[order[-1]]["argv"])
        # Under the deploy lock, with the backup container stopped and recreated.
        self.assertIn("flock", run)
        self.assertLess(run.index("compose stop backup"), run.index("restore.sh"))
        self.assertLess(run.index("restore.sh"), run.index("--force-recreate"))
        self.assertIn("Safety backup: abc", result.stdout)
        self.assertFalse(self.find(calls, "destroy"))

    def test_restore_asks_first_and_refuses_unknown_snapshots(self):
        result, calls = self.run_server("restore", "abc", VPS="1")  # no tty, no --yes
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Aborted", result.stdout)
        self.assertFalse(self.find(calls, "backup now"))
        self.assertFalse(self.find(calls, "restore.sh"))
        for snapshot in ("ff00", "not-hex"):
            with self.subTest(snapshot=snapshot):
                result, calls = self.run_server("restore", snapshot, "--yes", VPS="1")
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.find(calls, "backup now"))
                self.assertFalse(self.find(calls, "restore.sh"))
        result, _ = self.run_server("restore", VPS="1")
        self.assertNotEqual(result.returncode, 0)

    def test_failed_safety_backup_or_restore_stops(self):
        result, calls = self.run_server("restore", "abc", "--yes", VPS="1", BACKUP_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.find(calls, "restore.sh"))
        result, calls = self.run_server("restore", "abc", "--yes", VPS="1", RESTORE_FAIL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Safety backup: abc", result.stderr)

    def test_restore_without_a_vps_starts_a_read_only_local_copy(self):
        for flags in ({}, {"LOCAL": "1"}):
            with self.subTest(**flags):
                result, calls = self.run_server("restore", "abc123", **flags)
                self.assertEqual(result.returncode, 0, result.stderr)
                deploy = calls[self.find(calls, "deploy.sh")[0]]
                self.assertEqual(deploy["argv"], ["deploy.sh", "RESTORE=abc123"])
                self.assertEqual(deploy["backups"], "")
                for text in ("ssh", "backup now", "tag --add", "apply"):
                    self.assertFalse(self.find(calls, text), text)

    def test_region_restore_on_the_vps(self):
        result, calls = self.run_server("restore", "abc", "--region", "nether", "-1", "511", "1", "--yes",
                                        VPS="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(self.find(calls, "tag --add pre-restore")[0], self.find(calls, "restore.sh regions")[0])
        run = " ".join(calls[self.find(calls, "restore.sh regions")[0]]["argv"])
        folder = "world/dimensions/minecraft/the_nether/region"
        # Blocks -2..0 x 510..512: regions -1 and 0 on both axes.
        for name in ("r.-1.0.mca", "r.-1.1.mca", "r.0.0.mca", "r.0.1.mca"):
            self.assertIn(f"{folder}/{name}", run)
        self.assertEqual(run.count(".mca"), 4)
        self.assertIn("compose stop backup", run)
        self.assertIn("Restored 4 region file(s)", result.stdout)

    def test_region_restore_needs_the_vps_and_valid_coordinates(self):
        result, calls = self.run_server("restore", "abc", "--region", "overworld", "0", "0", "--yes")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("runs on the VPS", result.stderr)
        self.assertFalse(self.find(calls, "deploy.sh"))
        for region in (("moon", "0", "0"), ("end", "1.5", "0"), ("end", "0")):
            with self.subTest(region=region):
                result, calls = self.run_server("restore", "abc", "--region", *region, "--yes", VPS="1")
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.find(calls, "backup now"))

    def test_rollback_on_the_vps_restores_the_newest_safety_backup(self):
        safety = json.dumps([{"id": "5afe02", "time": iso(-60)}, {"id": "5afe01", "time": iso(-7200)}])
        result, calls = self.run_server("rollback", "--yes", VPS="1", PRE_RESTORE=safety)
        self.assertEqual(result.returncode, 0, result.stderr)
        # A new safety backup first, so the rollback can be undone too.
        self.assertLess(self.find(calls, "tag --add pre-restore abc")[0],
                        self.find(calls, "restore.sh world 5afe02 --yes")[0])
        self.assertFalse(self.find(calls, "5afe01"))

    def test_rollback_without_a_vps_starts_it_from_the_safety_backup(self):
        safety = json.dumps([{"id": "5afe02", "time": iso(-60)}])
        result, calls = self.run_server("rollback", "--yes", PRE_RESTORE=safety)
        self.assertEqual(result.returncode, 0, result.stderr)
        listing = " ".join(calls[self.find(calls, "--entrypoint restic")[0]]["argv"])
        self.assertIn("--no-lock snapshots --tag pre-restore --host mc-backup-worker", listing)
        self.assertTrue(self.find(calls, "apply"))
        deploy = " ".join(calls[self.find(calls, "scripts/deploy.sh")[0]]["argv"])
        self.assertIn("RESTORE=5afe02", deploy)
        self.assert_no_secrets_in_argv(calls)

    def test_rollback_refuses_without_a_safety_backup_or_locally(self):
        result, calls = self.run_server("rollback", "--yes", VPS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no safety backup", result.stderr)
        self.assertFalse(self.find(calls, "backup now"))
        result, calls = self.run_server("rollback", "--yes", LOCAL="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.find(calls, "deploy.sh"))
        safety = json.dumps([{"id": "5afe02", "time": iso(-60)}])
        result, calls = self.run_server("rollback", PRE_RESTORE=safety)  # not confirmed
        self.assertIn("Aborted", result.stdout)
        self.assertFalse(self.find(calls, "apply"))

    def test_restores_stay_off_github(self):
        # The workflow offers only start and stop, and runs nothing else.
        workflow = (SERVER.parents[1] / ".github/workflows/server.yml").read_text()
        self.assertIn("options: [start, stop]", workflow)
        self.assertIn("set -- start vps; else set -- stop;", workflow)
        for command in ("rollback", "drill", "restore <", "set -- restore", "backups"):
            self.assertNotIn(command, workflow)

    def test_usage_lists_the_backup_commands(self):
        result, _ = self.run_server("help")
        for command in ("backups", "check", "drill", "restore <id>", "--region", "rollback", "tofu <args>"):
            self.assertIn(command, result.stdout)


if __name__ == "__main__":
    unittest.main()
