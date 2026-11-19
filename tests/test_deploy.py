import json
import os
from pathlib import Path
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
    sys.exit(1 if stage == "decrypt" else 0)
if name == "docker":
    if "--env-file" in args:
        path = Path(args[args.index("--env-file") + 1])
        assert path.stat().st_mode & 0o777 == 0o600
        assert Path(".env").read_text() == "OLD=preserved\n"
    if stage in ("config", "pull", "up") and stage in args:
        sys.exit(1)
    if "restore" in args:  # restic restore writes the world into data/minecraft
        Path("data/minecraft/world").mkdir(parents=True, exist_ok=True)
        Path("data/minecraft/world/level.dat").touch()
    if args[:1] == ["info"]:
        print("aarch64" if stage == "arm64" else "x86_64")
    if "snapshots" in args:
        print("[]" if stage == "no-snapshots" else '[{"id": "abc"}]')
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
        for key in ("RESTORE", "NEW_WORLD"):
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
