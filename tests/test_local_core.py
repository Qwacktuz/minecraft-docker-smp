import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("smp", ROOT / "scripts/smp.py")
smp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smp)


class LocalCoreTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for directory in ("instances", "release", "runtime"):
            shutil.copytree(ROOT / directory, self.root / directory)
        patcher = patch.object(smp, "ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_instance_config_rejects_collisions_and_production_role(self):
        a = self.root / "instances/local-a.toml"
        original = a.read_text()
        a.write_text(original.replace("25566", "25567"))
        with self.assertRaisesRegex(ValueError, "shared"):
            smp.check_instances()
        a.write_text(original.replace('role = "local"', 'role = "production"'))
        with self.assertRaisesRegex(ValueError, "local instances only"):
            smp.read_instance("local-a")

    def test_instance_path_and_mutable_release_rejected(self):
        with self.assertRaises(ValueError):
            smp.read_instance("../../production")
        p = self.root / "release/local-core.json"
        release = json.loads(p.read_text())
        release["image"] = "itzg/minecraft-server:latest"
        p.write_text(json.dumps(release))
        with self.assertRaisesRegex(ValueError, "immutable"):
            smp.read_instance("local-a")

    def test_missing_and_deleted_worlds_are_not_reinitialized(self):
        _, release = smp.read_instance("local-a")
        with self.assertRaises(FileNotFoundError):
            smp.check_state("local-a", release)
        state, _ = smp.paths("local-a")
        (state / "data").mkdir(parents=True)
        marker = {"instance": "local-a", "release_sha256": smp.release_hash(release),
                  "new_world_pending": False}
        (state / "instance.json").write_text(json.dumps(marker))
        with self.assertRaisesRegex(ValueError, "World is missing"):
            smp.check_state("local-a", release)

    def test_initialization_never_overwrites_existing_state(self):
        _, release = smp.read_instance("local-a")
        state, _ = smp.paths("local-a")
        state.mkdir(parents=True)
        sentinel = state / "existing-save"
        sentinel.write_text("keep")
        with patch.object(smp.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "never overwrites"):
                smp.initialize("local-a", release)
            run.assert_not_called()
        self.assertEqual(sentinel.read_text(), "keep")

    def test_docker_context_precedence_cannot_bypass_remote_guard(self):
        with patch.dict(os.environ, {"DOCKER_HOST": "unix:///tmp/local.sock",
                                     "DOCKER_CONTEXT": "production"}):
            with patch.object(smp.subprocess, "check_output", return_value="ssh://production"):
                with self.assertRaisesRegex(ValueError, "remote context"):
                    smp.require_local_docker()

    def test_cloud_and_provider_credentials_not_forwarded_to_docker(self):
        config, release = smp.read_instance("local-a")
        with patch.dict(os.environ, {"SOPS_AGE_KEY": "private", "R2_SECRET_ACCESS_KEY": "private",
                                     "HCLOUD_TOKEN": "private", "RCON_PASSWORD": "private"}):
            _, env = smp.compose("local-a", config, release)
        for key in ("SOPS_AGE_KEY", "R2_SECRET_ACCESS_KEY", "HCLOUD_TOKEN", "RCON_PASSWORD"):
            self.assertNotIn(key, env)

    def test_failed_boot_stops_container_and_preserves_pending_state(self):
        _, release = smp.read_instance("local-a")
        state, _ = smp.paths("local-a")
        (state / "data").mkdir(parents=True)
        marker = {"instance": "local-a", "release_sha256": smp.release_hash(release),
                  "new_world_pending": True}
        (state / "instance.json").write_text(json.dumps(marker))

        def execute(command, **kwargs):
            if "up" in command:
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0)

        with patch.dict(os.environ, {"RCON_PASSWORD": "test-password-" * 3}), \
                patch.object(smp, "require_local_docker"), \
                patch.object(smp.os, "getuid", return_value=1000), \
                patch.object(smp.subprocess, "run", side_effect=execute) as run, \
                patch("sys.argv", ["smp", "_start", "local-a"]):
            with self.assertRaises(subprocess.CalledProcessError):
                smp.main()
            self.assertEqual(run.call_args_list[-1].args[0][-1], "stop")
        self.assertEqual(json.loads((state / "instance.json").read_text()), marker)
        self.assertEqual((state / "runtime/rcon-password").stat().st_mode & 0o777, 0o600)

    def test_stop_remains_available_when_world_is_missing(self):
        with patch.object(smp, "require_local_docker"), \
                patch.object(smp.subprocess, "run") as run, \
                patch("sys.argv", ["smp", "stop", "local-a"]):
            smp.main()
        self.assertEqual(run.call_args.args[0][-1], "stop")

    @unittest.skipUnless(all(shutil.which(tool) for tool in ("sops", "secretspec", "age-keygen")),
                         "SOPS, SecretSpec with SOPS support, and age-keygen required")
    def test_real_sops_to_secretspec_roundtrip_with_disposable_identity(self):
        identity = self.root / "disposable-age-key"
        subprocess.run(["age-keygen", "-o", str(identity)], capture_output=True, check=True)
        recipient = subprocess.check_output(["age-keygen", "-y", str(identity)], text=True).strip()
        (self.root / ".sops.yaml").write_text(
            f'creation_rules:\n  - path_regex: .*\\.enc\\.env$\n    age: "{recipient}"\n')
        shutil.copy(ROOT / "secretspec.toml", self.root / "secretspec.toml")
        _, release = smp.read_instance("local-a")
        with patch.dict(os.environ, {"SOPS_AGE_KEY_FILE": str(identity)}, clear=False):
            smp.initialize("local-a", release)
        state, encrypted = smp.paths("local-a")
        self.assertIn("RCON_PASSWORD=ENC[", encrypted.read_text())
        self.assertEqual(encrypted.stat().st_mode & 0o777, 0o600)
        self.assertFalse((state / "runtime/rcon-password").exists())
        env = dict(os.environ, SOPS_AGE_KEY_FILE=str(identity),
                   XDG_CONFIG_HOME=str(self.root / "settings"),
                   XDG_CACHE_HOME=str(self.root / "cache"))
        result = subprocess.run(
            ["secretspec", "run", "--file", str(self.root / "secretspec.toml"),
             "--profile", "local", "--scope", "game", "--reason", "Local core integration test",
             "--provider", f"sops://{encrypted}?format=dotenv", "--", "python3", "-c",
             "import os; assert len(os.environ['RCON_PASSWORD']) >= 24"],
            env=env, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose CLI required")
    def test_rendered_instances_have_isolated_loopback_only_resources(self):
        rendered = []
        for name in ("local-a", "local-b"):
            config, release = smp.read_instance(name)
            command, env = smp.compose(name, config, release)
            result = subprocess.run(command + ["config", "--format", "json"], env=env,
                                    capture_output=True, text=True, check=True)
            document = json.loads(result.stdout)
            rendered.append(document)
            self.assertEqual(set(document["services"]), {"minecraft"})
            service = document["services"]["minecraft"]
            self.assertNotIn("container_name", service)
            self.assertNotIn("RCON_PASSWORD", service["environment"])
            self.assertEqual(service["ports"][0]["host_ip"], "127.0.0.1")
            self.assertEqual(len(service["ports"]), 1)
            self.assertFalse(service["volumes"][0]["bind"]["create_host_path"])
        self.assertNotEqual(rendered[0]["name"], rendered[1]["name"])
        self.assertNotEqual(rendered[0]["networks"], rendered[1]["networks"])
        a = rendered[0]["services"]["minecraft"]
        b = rendered[1]["services"]["minecraft"]
        self.assertNotEqual(a["volumes"][0]["source"], b["volumes"][0]["source"])
        self.assertNotEqual(a["ports"][0]["published"], b["ports"][0]["published"])


if __name__ == "__main__":
    unittest.main()
