"""scripts/publish-map.sh and publish-world.sh's upload, with a fake docker."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MOCK = r'''
import json
import os
import sys
args = sys.argv[1:]
keys = {name: os.environ.get(name) for name in
        ("RCLONE_CONFIG_R2_ACCESS_KEY_ID", "RCLONE_CONFIG_R2_SECRET_ACCESS_KEY", "RCLONE_CONFIG_R2_ENDPOINT")}
with open(os.environ["MOCK_LOG"], "a") as log:
    log.write(json.dumps({"argv": args, "keys": keys}) + "\n")
if args[:2] == ["compose", "ps"] and os.environ.get("GAME_RUNNING"):
    print("minecraft-service")
'''
ENV = ("R2_ENDPOINT=https://r2.invalid\nR2_ACCESS_KEY_ID=key-id\n"
       "R2_SECRET_ACCESS_KEY=secret-key\n")


class PublishTests(unittest.TestCase):
    def run_script(self, script, bucket="pub", web=True, world=False, **env):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        app = Path(temp.name)
        (app / "scripts").mkdir()
        for name in (script, "lib.sh", "world_zip.py"):
            shutil.copy(ROOT / "scripts" / name, app / "scripts" / name)
        (app / ".env").write_text(ENV + (f"PUBLIC_WORLD_BUCKET={bucket}\n" if bucket else ""))
        if web:
            maps = app / "data/minecraft/bluemap/web/maps/world"
            maps.mkdir(parents=True)
            (maps.parents[1] / "index.html").write_text("<html>")
            (maps.parents[1] / "settings.json").write_text("{}")
        if world:
            (app / "data/minecraft/world").mkdir(parents=True)
            (app / "data/minecraft/world/level.dat").write_bytes(b"level")
        mocks = app / "mocks"
        mocks.mkdir()
        (mocks / "docker").write_text(f"#!{sys.executable}\n" + MOCK)
        (mocks / "docker").chmod(0o755)
        log = app / "calls.jsonl"
        log.touch()
        run_env = dict(os.environ, APP_DIR=str(app), MOCK_LOG=str(log),
                       PATH=f"{mocks}:{os.environ['PATH']}", **env)
        result = subprocess.run(["bash", str(app / "scripts" / script)], env=run_env,
                                capture_output=True, text=True)
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        return app, result, [call for call in calls if call["argv"][:1] == ["run"]]

    def assert_keys_by_name_only(self, run):
        self.assertEqual(run["keys"], {"RCLONE_CONFIG_R2_ACCESS_KEY_ID": "key-id",
                                       "RCLONE_CONFIG_R2_SECRET_ACCESS_KEY": "secret-key",
                                       "RCLONE_CONFIG_R2_ENDPOINT": "https://r2.invalid"})
        self.assertNotIn("secret-key", " ".join(run["argv"]))
        self.assertNotIn("key-id", " ".join(run["argv"]))

    def test_publishes_the_web_map_under_map(self):
        app, result, runs = self.run_script("publish-map.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(runs), 1)
        argv = runs[0]["argv"]
        self.assertIn(f"{app}/data/minecraft/bluemap/web:/work:ro", argv)
        image = next(arg for arg in argv if arg.startswith("rclone/rclone:"))
        rclone = argv[argv.index(image) + 1:]
        # copy (never sync), from the mount to the bucket's map/ prefix.
        self.assertEqual(rclone[:3], ["copy", "/work", "r2:pub/map"])
        self.assertIn("sql.php", rclone)
        # The browser decompresses the tiles; a Content-Encoding header would break that.
        self.assertNotIn("Content-Encoding", " ".join(rclone))
        self.assert_keys_by_name_only(runs[0])

    def test_skips_without_a_bucket_or_a_map(self):
        _, result, runs = self.run_script("publish-map.sh", bucket="")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("not publishing the map", result.stdout)
        self.assertEqual(runs, [])
        _, result, runs = self.run_script("publish-map.sh", web=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no map to publish", result.stdout)
        self.assertEqual(runs, [])

    def test_refuses_while_the_game_runs(self):
        _, result, runs = self.run_script("publish-map.sh", GAME_RUNNING="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("the game is running", result.stderr)
        self.assertEqual(runs, [])

    def test_world_zip_upload_uses_the_shared_rclone_helper(self):
        app, result, runs = self.run_script("publish-world.sh", web=False, world=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        argv = runs[-1]["argv"]
        self.assertIn(f"{app}/.cache:/upload:ro", argv)
        self.assertIn("--user", argv)
        image = next(arg for arg in argv if arg.startswith("rclone/rclone:"))
        self.assertEqual(argv[argv.index(image) + 1:argv.index(image) + 4],
                         ["copyto", "/upload/world.zip", "r2:pub/world.zip"])
        self.assert_keys_by_name_only(runs[-1])


if __name__ == "__main__":
    unittest.main()
