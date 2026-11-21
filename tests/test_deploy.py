import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


DEPLOY = Path(__file__).resolve().parents[1] / "scripts/deploy.sh"
MOCK = r'''
import json
import os
from pathlib import Path
import sys

name = Path(sys.argv[0]).name
args = sys.argv[1:]
stage = os.environ.get("FAIL_STAGE", "")
with open(os.environ["MOCK_LOG"], "a") as log:
    log.write(json.dumps([name, *args]) + "\n")
if name == "sops":
    if stage != "empty":
        print("DUMMY=fixture")
        print("R2_ENDPOINT=https://r2.invalid\nR2_BUCKET_NAME=b\nRESTIC_PASSWORD=p")
        print("R2_ACCESS_KEY_ID=k\nR2_SECRET_ACCESS_KEY=s")
        if os.environ.get("MOCK_PUBLIC"):
            print("PUBLIC_WORLD_BUCKET=pub")
    sys.exit(1 if stage == "decrypt" else 0)
if name == "docker":
    if "--env-file" in args:
        path = Path(args[args.index("--env-file") + 1])
        assert path.stat().st_mode & 0o777 == 0o600
        assert Path(".env").read_text() == "OLD=preserved\n"
    if stage in ("config", "pull", "up") and stage in args:
        sys.exit(1)
    if "--entrypoint" in args and os.environ.get("REPO_LOG"):
        with open(os.environ["REPO_LOG"], "a") as seen:
            seen.write(f"{os.environ['RESTIC_REPOSITORY']} {os.environ['AWS_ACCESS_KEY_ID']}\n")
    if stage == "map-pull" and "r2:pub/map" in args:
        sys.exit(1)
    if "r2:pub/map-state.tar" in args and os.environ.get("MOCK_ARCHIVE"):
        Path("data").mkdir(exist_ok=True)
        Path("data/map-state.tar").touch()  # rclone with no archive exits 0 and writes nothing
    if any("tar -C" in arg for arg in args) and stage == "untar":
        sys.exit(1)
    if "r2:pub/map" in args and os.environ.get("RCLONE_LOG"):
        with open(os.environ["RCLONE_LOG"], "a") as seen:
            seen.write(f"{os.environ['RCLONE_CONFIG_R2_ACCESS_KEY_ID']} {os.environ['RCLONE_CONFIG_R2_ENDPOINT']}\n")
    if "restore" in args and stage == "restore":
        sys.exit(1)
    if "restore" in args:  # restic restore writes the world into data/minecraft
        Path("data/minecraft/world").mkdir(parents=True, exist_ok=True)
        Path("data/minecraft/world/level.dat").touch()
    if args[:1] == ["info"]:
        print("aarch64" if stage == "arm64" else "x86_64")
    if "snapshots" in args:
        print("[]" if stage == "no-snapshots" else
              '[{"id": "abc", "time": "2026-11-19T12:00:00Z"}, {"id": "def456", "time": "2026-11-18T12:00:00Z"}]')
    if "ps" in args:
        print("minecraft-service")
'''


class DeployTests(unittest.TestCase):
    def run_deploy(self, stage="", world=True, **extra):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        binary = root / "bin"
        binary.mkdir()
        for name in ("sops", "docker", "sleep"):
            path = binary / name
            path.write_text(f"#!{sys.executable}\n" + MOCK)
            path.chmod(0o755)
        (root / ".env").write_text("OLD=preserved\n")
        if world:
            (root / "data/minecraft/world").mkdir(parents=True)
            (root / "data/minecraft/world/level.dat").touch()
        log = root / "commands.jsonl"
        env = dict(os.environ, APP_DIR=str(root), FAIL_STAGE=stage,
                   MOCK_LOG=str(log),
                   PATH=f"{binary}:{os.environ['PATH']}", **extra)
        for key in ("RESTORE", "NEW_WORLD", "BACKUPS", "RESTIC_SOURCE", "MOCK_PUBLIC", "MOCK_ARCHIVE", "RCLONE_LOG", "PHASE_LOG", "GITHUB_STEP_SUMMARY"):
            if key not in extra:
                env.pop(key, None)
        result = subprocess.run(["bash", str(DEPLOY)], env=env,
                                capture_output=True, text=True)
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual(list(root.glob(".env.*")), [])
        self.assertFalse((root / "age.key").exists())
        return root, result, calls

    def test_preflight_failures_preserve_environment(self):
        for stage in ("decrypt", "empty", "config", "pull"):
            with self.subTest(stage=stage):
                root, result, calls = self.run_deploy(stage)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((root / ".env").read_text(), "OLD=preserved\n")
                self.assertFalse(any("up" in call or "exec" in call for call in calls))

    def test_success_uses_service_name_and_waits_for_health(self):
        root, result, calls = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((root / ".env").stat().st_mode & 0o777, 0o600)
        self.assertTrue(any("save-all flush" in call for call in calls))
        self.assertTrue(any("up" in call and "--wait" in call for call in calls))
        for call in calls:
            if "exec" in call:
                self.assertIn("minecraft-service", call)
            self.assertNotIn("prune", call)

    def test_restore_latest_happens_before_up(self):
        _, result, calls = self.run_deploy(RESTORE="latest")
        self.assertEqual(result.returncode, 0, result.stderr)
        index = lambda match: next(i for i, call in enumerate(calls) if match(call))
        restore = index(lambda call: "restore" in call and "latest" in call)
        move = index(lambda call: any("minecraft.previous" in arg for arg in call))
        up = index(lambda call: "up" in call)
        self.assertLess(move, restore)
        self.assertLess(restore, up)
        for call in calls:  # secrets are passed by name, never as values
            self.assertNotIn("RESTIC_PASSWORD=p", call)
            self.assertFalse(any(arg.endswith("=s") for arg in call))

    def test_restore_pulls_the_published_map_before_up(self):
        keys = Path(tempfile.mkdtemp()) / "keys"
        self.addCleanup(shutil.rmtree, keys.parent)
        _, result, calls = self.run_deploy(RESTORE="latest", MOCK_PUBLIC="1", RCLONE_LOG=str(keys))
        self.assertEqual(result.returncode, 0, result.stderr)
        index = lambda match: next(i for i, call in enumerate(calls) if match(call))
        pull = index(lambda call: "r2:pub/map" in call)
        restore = index(lambda call: "restore" in call and "latest" in call)
        # Side by side with the restore, after the old world moved aside, and
        # both finish before the owner fix and the start.
        self.assertLess(index(lambda call: any("minecraft.previous" in arg for arg in call)), pull)
        chown = index(lambda call: any("chown" in arg for arg in call))
        self.assertLess(max(pull, restore), chown)
        self.assertLess(pull, index(lambda call: "up" in call))
        self.assertEqual(calls[pull][calls[pull].index("r2:pub/map") + 1], "/data/bluemap/web")
        self.assertIn("copy", calls[pull])  # never sync: nothing is deleted
        self.assertEqual(keys.read_text(), "k https://r2.invalid\n")
        self.assertFalse(any(arg.endswith("=s") or arg.endswith("=k") for arg in calls[pull]))
        # No restore (a redeploy) or no public bucket: no pull.
        _, result, calls = self.run_deploy(MOCK_PUBLIC="1")
        self.assertFalse(any("r2:pub/map" in call for call in calls))
        _, result, calls = self.run_deploy(RESTORE="latest")
        self.assertFalse(any(any(arg.startswith("r2:") for arg in call) for call in calls))

    def test_a_failed_restore_stops_after_the_map_pull(self):
        _, result, calls = self.run_deploy("restore", RESTORE="latest", MOCK_PUBLIC="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("The restore of latest failed", result.stderr)
        self.assertTrue(any("r2:pub/map" in call for call in calls))
        self.assertFalse(any("up" in call for call in calls))

    def test_phases_are_timed(self):
        timings = Path(tempfile.mkdtemp()) / "timings"
        self.addCleanup(shutil.rmtree, timings.parent)
        _, result, _ = self.run_deploy(RESTORE="latest", MOCK_PUBLIC="1", PHASE_LOG=str(timings))
        self.assertEqual(result.returncode, 0, result.stderr)
        names = [line.split()[0] for line in timings.read_text().splitlines()]
        self.assertEqual(sorted(names), sorted(
            ["decrypt", "image-pull", "restic-restore", "map-pull", "chown", "compose-up"]))
        for line in timings.read_text().splitlines():
            self.assertRegex(line, r"^[a-z-]+ \d+$")
        self.assertRegex(result.stdout, r"(?m)^--- compose-up \d+s$")

    def test_owner_fix_changes_only_files_with_another_owner(self):
        _, result, calls = self.run_deploy(RESTORE="latest")
        chown = next(call for call in calls if any("chown" in arg for arg in call))
        self.assertIn("! -user 1000 -o ! -group 1000", chown[-1])
        self.assertNotIn("chown -R", chown[-1])

    def test_the_map_archive_replaces_the_file_by_file_pull(self):
        _, result, calls = self.run_deploy(RESTORE="latest", MOCK_PUBLIC="1", MOCK_ARCHIVE="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        download = next(call for call in calls if "r2:pub/map-state.tar" in call)
        self.assertEqual(download[download.index("r2:pub/map-state.tar") - 1:][:3],
                         ["copyto", "r2:pub/map-state.tar", "/data/map-state.tar"])
        unpack = next(call for call in calls if any("tar -C" in arg for arg in call))
        self.assertIn("WEB=/data/minecraft/bluemap/web", unpack)
        self.assertFalse(any("r2:pub/map" in call for call in calls))  # no file-by-file pull
        self.assertIn("Unpacked the map archive", result.stdout)

    def test_without_the_archive_the_files_are_pulled(self):
        _, result, calls = self.run_deploy(RESTORE="latest", MOCK_PUBLIC="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("could not unpack", result.stderr)  # no archive is no warning
        self.assertTrue(any("r2:pub/map" in call for call in calls))
        self.assertFalse(any(any("tar -C" in arg for arg in call) for call in calls))
        _, result, calls = self.run_deploy("untar", RESTORE="latest", MOCK_PUBLIC="1", MOCK_ARCHIVE="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("could not unpack the map archive", result.stderr)
        self.assertTrue(any("r2:pub/map" in call for call in calls))

    def test_a_failed_map_pull_only_warns(self):
        _, result, calls = self.run_deploy("map-pull", RESTORE="latest", MOCK_PUBLIC="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("could not pull the published map", result.stderr)
        self.assertTrue(any("up" in call for call in calls))

    def test_restore_is_read_only_and_limited_to_vps_snapshots(self):
        _, result, calls = self.run_deploy(RESTORE="latest")
        self.assertEqual(result.returncode, 0, result.stderr)
        for call in calls:
            if "restore" in call or "snapshots" in call:
                self.assertIn("--no-lock", call)
                self.assertEqual(call[call.index("--host") + 1], "mc-backup-worker")

    def test_restore_a_snapshot_id_only_from_the_vps_host(self):
        _, result, calls = self.run_deploy(RESTORE="def4")
        self.assertEqual(result.returncode, 0, result.stderr)
        restore = next(call for call in calls if "restore" in call)
        self.assertEqual(restore[restore.index("restore") + 1], "def456")
        self.assertEqual(restore[restore.index("--host") + 1], "mc-backup-worker")
        # Not in the host-filtered list (another host's snapshot, or a typo): stop.
        _, result, calls = self.run_deploy(RESTORE="0bad")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No single mc-backup-worker snapshot", result.stderr)
        self.assertFalse(any("restore" in call or "up" in call for call in calls))

    def test_vault_restores_read_the_vault_bucket_with_its_own_keys(self):
        repositories = Path(tempfile.mkdtemp()) / "repos"
        self.addCleanup(shutil.rmtree, repositories.parent)
        _, result, calls = self.run_deploy(
            RESTORE="latest", RESTIC_SOURCE="vault", VAULT_ACCESS_KEY_ID="vk",
            VAULT_SECRET_ACCESS_KEY="vs", REPO_LOG=str(repositories))
        self.assertEqual(result.returncode, 0, result.stderr)
        seen = repositories.read_text().splitlines()
        self.assertTrue(seen)
        for line in seen:
            self.assertEqual(line, "s3:https://r2.invalid/cactuz-mc-vault vk")
        for call in calls:
            self.assertNotIn("vs", call)

    def test_only_backups_1_enables_the_backup_service(self):
        root, result, calls = self.run_deploy(BACKUPS="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("COMPOSE_PROFILES=backup", (root / ".env").read_text())
        self.assertFalse(any("rm" in call for call in calls))
        root, result, calls = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("COMPOSE_PROFILES", (root / ".env").read_text())
        # A leftover backup container is removed, so a local copy never uploads.
        self.assertTrue(any("rm" in call and "backup" in call for call in calls))

    def test_restore_without_snapshots_needs_new_world(self):
        _, result, calls = self.run_deploy("no-snapshots", RESTORE="latest")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("NEW_WORLD=1", result.stderr)
        self.assertFalse(any("up" in call or "restore" in call for call in calls))
        _, result, calls = self.run_deploy("no-snapshots", RESTORE="latest", NEW_WORLD="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any("restore" in call for call in calls))

    def test_arm64_hosts_use_aikar_flags(self):
        root, result, _ = self.run_deploy("arm64")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("USE_MEOWICE_FLAGS=false\nUSE_AIKAR_FLAGS=true", (root / ".env").read_text())
        root, result, _ = self.run_deploy()
        self.assertNotIn("USE_MEOWICE_FLAGS", (root / ".env").read_text())

    def test_missing_world_is_never_started(self):
        _, result, calls = self.run_deploy(world=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No world", result.stderr)
        self.assertFalse(any("up" in call for call in calls))
        _, result, _ = self.run_deploy(world=False, RESTORE="latest")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_health_failure_is_not_reported_as_success(self):
        _, result, calls = self.run_deploy("up")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Deployment completed", result.stdout)
        self.assertFalse(any("say Deployment complete." in call for call in calls))



if __name__ == "__main__":
    unittest.main()
