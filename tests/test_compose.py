import json
import re
import os
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "MC_WHITELIST", "RCON_PASSWORD",
    "R2_ENDPOINT", "R2_BUCKET_NAME", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
    "RESTIC_PASSWORD",
)


@unittest.skipUnless(shutil.which("docker"), "Docker Compose CLI required; no daemon needed")
class ComposeTests(unittest.TestCase):
    def render(self, overrides=None, profiles="backup"):
        env = dict(os.environ, COMPOSE_PROFILES=profiles)
        for key in REQUIRED:
            env[key] = "validation-placeholder"
        env.update(MC_OPS="")
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

    def test_only_game_and_backup_with_public_game_ports(self):
        result = self.render()
        self.assertEqual(result.returncode, 0, result.stderr)
        services = json.loads(result.stdout)["services"]
        self.assertEqual(set(services), {"minecraft-service", "backup"})
        ports = {port["target"] for port in services["minecraft-service"]["ports"]}
        self.assertEqual(ports, {25565, 24454, 25454})  # game, voice chat, webcam
        self.assertNotIn("ports", services["backup"])
        for service in services.values():
            self.assertEqual(service["logging"]["driver"], "local")
            self.assertEqual(service["logging"]["options"]["max-file"], "3")
        self.assertEqual(services["minecraft-service"]["stop_grace_period"], "2m0s")
        self.assertEqual(services["minecraft-service"]["environment"]["VERSION"], "26.3")
        self.assertTrue(services["backup"]["volumes"][0]["read_only"])

    def test_backups_run_only_with_the_backup_profile(self):
        result = self.render(profiles="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(json.loads(result.stdout)["services"]), {"minecraft-service"})

    def test_backups_use_one_restic_host_and_keep_pre_prune_snapshots(self):
        result = self.render()
        backup = json.loads(result.stdout)["services"]["backup"]["environment"]
        self.assertIn("--keep-tag pre-prune", backup["PRUNE_RESTIC_RETENTION"])
        host = backup["RESTIC_HOST"]
        self.assertIn(f"WORLD_HOST={host}", (ROOT / "scripts/lib.sh").read_text())
        # bin/server reads it from scripts/lib.sh rather than defining its own.
        server = (ROOT / "bin/server").read_text()
        self.assertIn('. "$ROOT/scripts/lib.sh"', server)
        self.assertNotIn("WORLD_HOST=", server)

    def test_every_image_is_pinned_by_digest(self):
        services = json.loads(self.render().stdout)["services"]
        for name, service in services.items():
            self.assertRegex(service["image"], r":[^@]+@sha256:[0-9a-f]{64}$", name)
        lib = (ROOT / "scripts/lib.sh").read_text()
        images = dict(re.findall(r"^([A-Z]+_IMAGE)=(\S+)$", lib, re.M))
        self.assertEqual(set(images), {"BACKUP_IMAGE", "ALPINE_IMAGE", "JAVA_IMAGE", "RCLONE_IMAGE"})
        for image in images.values():
            self.assertRegex(image, r":[^@]+@sha256:[0-9a-f]{64}$")
        self.assertEqual(services["backup"]["image"], images["BACKUP_IMAGE"])
        # Scripts use the pinned variables, never a bare image name.
        for script in (ROOT / "scripts").glob("*.sh"):
            if script.name != "lib.sh":
                self.assertNotRegex(script.read_text(), r"(itzg/|alpine[ :]|eclipse-temurin|rclone/rclone)",
                                    script.name)


if __name__ == "__main__":
    unittest.main()
