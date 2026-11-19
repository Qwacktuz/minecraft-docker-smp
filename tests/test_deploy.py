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
if name == "tailscale":
    print(os.environ.get("MOCK_TS_IP", "100.100.1.2"))
if name == "docker":
    if "--env-file" in args:
        path = Path(args[args.index("--env-file") + 1])
        assert path.stat().st_mode & 0o777 == 0o600
        assert Path(".env").read_text() == "OLD=preserved\n"
    if stage in ("config", "pull", "up") and stage in args:
        sys.exit(1)
    if "snapshots" in args:
        print("[]" if stage == "no-snapshots" else '[{"id": "abc"}]')
    if "inspect" in args:
        print("" if stage == "legacy-loki" else "bind")
    if "ps" in args and "--quiet" in args:
        if stage in ("legacy-loki", "configured-loki"):
            print("loki-container-id")
    elif "ps" in args:
        print("minecraft-service")
'''


class DeployTests(unittest.TestCase):
    def run_deploy(self, stage="", ip="100.100.1.2", **extra):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        binary = root / "bin"
        binary.mkdir()
        for name in ("sops", "tailscale", "docker", "sleep"):
            path = binary / name
            path.write_text(f"#!{sys.executable}\n" + MOCK)
            path.chmod(0o755)
        (root / ".env").write_text("OLD=preserved\n")
        log = root / "commands.jsonl"
        env = dict(os.environ, APP_DIR=str(root), FAIL_STAGE=stage,
                   MOCK_LOG=str(log), MOCK_TS_IP=ip,
                   PATH=f"{binary}:{os.environ['PATH']}", **extra)
        for key in ("TS_IP", "RESTORE", "NEW_WORLD"):
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

    def test_invalid_tailnet_addresses_stop_before_compose(self):
        for ip in ("", "127.0.0.1", "100.63.1.2", "100.128.1.2",
                   "100.100.256.2", "100.100.1.2\n100.100.1.3"):
            with self.subTest(ip=ip):
                root, result, calls = self.run_deploy(ip=ip)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual((root / ".env").read_text(), "OLD=preserved\n")
                self.assertFalse(any(call[0] == "docker" for call in calls))

    def test_success_uses_service_name_and_waits_for_health(self):
        root, result, calls = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((root / ".env").stat().st_mode & 0o777, 0o600)
        self.assertIn("TS_IP=100.100.1.2", (root / ".env").read_text())
        self.assertTrue(any("save-all flush" in call for call in calls))
        self.assertTrue(any("up" in call and "--wait" in call for call in calls))
        for call in calls:
            if "exec" in call:
                self.assertIn("minecraft-service", call)
            self.assertNotIn("prune", call)

    def test_local_loopback_skips_tailscale(self):
        root, result, calls = self.run_deploy(TS_IP="127.0.0.1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("TS_IP=127.0.0.1", (root / ".env").read_text())
        self.assertFalse(any(call[0] == "tailscale" for call in calls))

    def test_preset_non_loopback_ip_is_still_checked(self):
        _, result, calls = self.run_deploy(TS_IP="8.8.8.8", ip="8.8.8.8")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(call[0] == "tailscale" for call in calls))

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

    def test_health_failure_is_not_reported_as_success(self):
        _, result, calls = self.run_deploy("up")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Deployment completed", result.stdout)
        self.assertFalse(any("say Deployment complete." in call for call in calls))

    def test_legacy_loki_blocks_recreation(self):
        root, result, calls = self.run_deploy("legacy-loki")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("loki-migration.md", result.stderr)
        self.assertEqual((root / ".env").read_text(), "OLD=preserved\n")
        self.assertFalse(any("up" in call or "pull" in call for call in calls))

    def test_configured_loki_allows_deployment(self):
        _, result, _ = self.run_deploy("configured-loki")
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
