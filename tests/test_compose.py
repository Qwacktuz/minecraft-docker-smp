import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "TS_IP", "MC_WHITELIST", "RCON_PASSWORD", "GRAFANA_PASSWORD",
    "R2_ENDPOINT", "R2_BUCKET_NAME", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
    "RESTIC_PASSWORD", "ARCANE_ENCRYPTION_KEY", "ARCANE_JWT_SECRET",
)


@unittest.skipUnless(shutil.which("docker"), "Docker Compose CLI required; no daemon needed")
class ComposeTests(unittest.TestCase):
    def render(self, overrides=None):
        env = dict(os.environ)
        for key in REQUIRED:
            env[key] = "validation-placeholder"
        env.update(TS_IP="127.0.0.1", MC_OPS="")
        env.update(overrides or {})
        return subprocess.run(
            ["docker", "compose", "--env-file", os.devnull, "-f", str(ROOT / "compose.yml"),
             "config", "--format", "json"],
            env=env, capture_output=True, text=True, cwd=ROOT,
        )

    def test_missing_required_values_fail_closed(self):
        for key in REQUIRED:
            with self.subTest(key=key):
                result = self.render({key: ""})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(key, result.stderr)

    def test_admin_ports_shutdown_and_log_limits(self):
        result = self.render()
        self.assertEqual(result.returncode, 0, result.stderr)
        services = json.loads(result.stdout)["services"]
        self.assertEqual(len(services), 7)
        public_ports = {25565, 24454, 25454}
        for name, service in services.items():
            for port in service.get("ports", []):
                if port["target"] not in public_ports:
                    self.assertEqual(port["host_ip"], "127.0.0.1", name)
            self.assertEqual(service["logging"]["driver"], "local")
            self.assertEqual(service["logging"]["options"]["max-file"], "3")
        self.assertEqual(services["minecraft-service"]["stop_grace_period"], "2m0s")
        self.assertEqual(services["minecraft-service"]["environment"]["VERSION"], "26.3")
        self.assertTrue(services["backup"]["volumes"][0]["read_only"])


if __name__ == "__main__":
    unittest.main()
