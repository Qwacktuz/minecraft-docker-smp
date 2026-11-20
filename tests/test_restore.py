"""scripts/restore.sh with a mock docker; nothing real runs."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/restore.sh"
MOCK = r'''
import json, os, sys
with open(os.environ["MOCK_LOG"], "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\n")
if "ls -1d" in " ".join(sys.argv):
    print(os.environ.get("PREVIOUS", ""))
if "snapshots" in sys.argv:
    # Only snapshots of the VPS host are listed (restic filters by --host).
    print(os.environ.get("SNAP_JSON") or json.dumps([
        {"id": FULL, "time": "2026-11-19T12:00:00Z"},
        {"id": "abd0000011112222", "time": "2026-11-18T12:00:00Z"}]))
'''
FULL = "abcdef1234567890"


class RestoreTests(unittest.TestCase):
    def run_restore(self, *argv, stdin="", **env):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / ".env").write_text("R2_ENDPOINT=e\nR2_BUCKET_NAME=b\nR2_ACCESS_KEY_ID=i\n"
                                   "R2_SECRET_ACCESS_KEY=s\nRESTIC_PASSWORD=p\n")
        mocks = root / "mocks"
        mocks.mkdir()
        (mocks / "docker").write_text(f"#!{sys.executable}\nFULL = {FULL!r}\n" + MOCK)
        (mocks / "docker").chmod(0o755)
        log = root / "calls.jsonl"
        log.touch()
        result = subprocess.run(
            ["bash", str(SCRIPT), *argv], input=stdin, capture_output=True, text=True,
            env=dict(os.environ, APP_DIR=str(root), MOCK_LOG=str(log),
                     PATH=f"{mocks}:{os.environ['PATH']}", **env))
        return result, [" ".join(call) for call in map(json.loads, log.read_text().splitlines())]

    def test_unknown_or_missing_command_shows_usage(self):
        for argv in ((), ("launch",), ("regions", "abc")):
            with self.subTest(argv=argv):
                result, calls = self.run_restore(*argv)
                self.assertEqual(result.returncode, 2)
                self.assertIn("restore.sh world", result.stderr)
                self.assertEqual(calls, [])

    def test_regions_restores_region_entities_and_poi(self):
        result, calls = self.run_restore(
            "regions", "abcdef123456", "world/dimensions/minecraft/overworld/region/r.2.-1.mca")
        self.assertEqual(result.returncode, 0, result.stderr)
        restore = next(call for call in calls if " restore abcdef123456" in call)
        for kind in ("region", "entities", "poi"):
            self.assertIn(f"--include /data/world/dimensions/minecraft/overworld/{kind}/r.2.-1.mca", restore)
        self.assertLess(calls.index("compose stop minecraft-service"), calls.index(restore))
        self.assertIn("from abcdef12.", result.stdout)

    def test_regions_rejects_other_paths(self):
        result, calls = self.run_restore("regions", "abc", "world/level.dat")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, [])

    def test_world_moves_the_old_world_aside_first(self):
        result, calls = self.run_restore("world", "abc", "--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        aside = next(i for i, call in enumerate(calls) if "minecraft_pre_restore_" in call)
        restore = next(i for i, call in enumerate(calls) if f" restore {FULL} --host mc-backup-worker" in call)
        self.assertLess(aside, restore)
        self.assertTrue(calls[-1].startswith("compose up -d --wait"))

    def test_restores_only_use_a_single_vps_snapshot(self):
        # The ID is resolved against the host-filtered list, so a snapshot of
        # another host (absent from it), or an ambiguous prefix, is refused.
        for snapshot in ("0123abcd", "ab", "not-hex"):
            for argv in (("world", snapshot, "--yes"),
                         ("regions", snapshot, "world/dimensions/minecraft/the_end/region/r.0.0.mca")):
                with self.subTest(argv=argv):
                    result, calls = self.run_restore(*argv)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("No single mc-backup-worker snapshot", result.stderr)
                    self.assertFalse([call for call in calls if " restore " in f" {call} " or "compose" in call])
        listing = next(call for call in self.run_restore("world", "abc", "--yes")[1] if "snapshots" in call)
        self.assertIn("--no-lock snapshots --host mc-backup-worker --json", listing)

    def test_latest_resolves_to_the_newest_vps_snapshot(self):
        result, calls = self.run_restore("world", "latest", "--yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue([call for call in calls if f" restore {FULL} --host mc-backup-worker" in call])

    def test_world_and_rollback_ask_first(self):
        result, calls = self.run_restore("world", "abc", stdin="n\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Aborted", result.stdout)
        self.assertEqual([call for call in calls if "snapshots" not in call], [])
        result, calls = self.run_restore("rollback", stdin="n\n", PREVIOUS="/d/minecraft_pre_restore_1")
        self.assertIn("Aborted", result.stdout)
        self.assertFalse([call for call in calls if "compose" in call])

    def test_rollback_puts_the_newest_copy_back(self):
        result, calls = self.run_restore("rollback", stdin="y\n", PREVIOUS="/d/minecraft_pre_restore_2")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue([call for call in calls if "mv /d/minecraft_pre_restore_2 /d/minecraft" in call])
        result, _ = self.run_restore("rollback")
        self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
