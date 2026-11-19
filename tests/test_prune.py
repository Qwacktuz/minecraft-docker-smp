"""scripts/prune_plan.py: keep rules, player data and deletion selections."""

import gzip
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import prune_plan  # noqa: E402

SETTINGS = {
    "PRUNE_MIN_INHABITED": "10 minutes", "PRUNE_UNTOUCHED_DAYS": "60",
    "PRUNE_PLAYER_RADIUS": "12", "PRUNE_BUFFER": "4", "PRUNE_MAX_PERCENT": "98",
}


# --- A tiny NBT writer for fixture player files ---------------------------------

def nbt_string(value):
    data = value.encode()
    return struct.pack(">H", len(data)) + data


def nbt_payload(value):
    """(tag id, payload bytes) for the few types the fixtures need."""
    if isinstance(value, str):
        return 8, nbt_string(value)
    if isinstance(value, float):
        return 6, struct.pack(">d", value)
    if isinstance(value, int):
        return 3, struct.pack(">i", value)
    if isinstance(value, tuple):  # int array
        return 11, struct.pack(">i", len(value)) + b"".join(struct.pack(">i", v) for v in value)
    if isinstance(value, list):  # list of doubles
        return 9, struct.pack(">bi", 6, len(value)) + b"".join(struct.pack(">d", v) for v in value)
    if isinstance(value, dict):
        body = b""
        for key, item in value.items():
            tag, payload = nbt_payload(item)
            body += struct.pack(">b", tag) + nbt_string(key) + payload
        return 10, body + b"\0"
    raise TypeError(value)


def player_file(path, data):
    path.write_bytes(gzip.compress(b"\x0a" + nbt_string("") + nbt_payload(data)[1]))


def region_file(path, chunks):
    """An .mca whose header marks the given local chunk indexes as present."""
    header = bytearray(8192)
    for index in chunks:
        struct.pack_into(">I", header, index * 4, (2 << 8) | 1)
    path.write_bytes(bytes(header))


class PrunePlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.world = Path(self.temp.name)
        (self.world / "players/data").mkdir(parents=True)
        self.region = self.world / "dimensions/minecraft/overworld/region"
        self.region.mkdir(parents=True)
        patcher = unittest.mock.patch.dict(os.environ, SETTINGS)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_players_and_respawn_points_are_protected_per_dimension(self):
        uuid = "0f75a81d-70e5-43c5-b892-f33c524284f2"
        player_file(self.world / f"players/data/{uuid}.dat", {
            "Dimension": "minecraft:the_nether", "Pos": [-259.3, 130.0, 55.7],
            "respawn": {"dimension": "minecraft:overworld", "pos": (100, 64, -40)},
        })
        (self.world / "players/data/broken.dat").write_bytes(b"not nbt")
        self.assertEqual(prune_plan.player_points(self.world, "the_nether"), [(-259.3, 55.7)])
        self.assertEqual(prune_plan.player_points(self.world, "overworld"), [(100, -40)])
        self.assertEqual(prune_plan.circles(self.world, "the_nether", None), [(-17, 3, 12)])

    def test_queries_combine_every_rule(self):
        protect = self.world / "protect.txt"
        protect.write_text("# spawn\noverworld 0 0 256\nthe_end 0 0 320 # island\n")
        keep = prune_plan.query("keep", self.world, "overworld", protect, now=1_000_000_000)
        self.assertEqual(keep, 'InhabitedTime >= "10 minutes" OR Timestamp >= "994816000" '
                               'OR Circle contains "0;0;16"')
        candidates = prune_plan.query("candidates", self.world, "overworld", protect, now=1_000_000_000)
        self.assertEqual(candidates, 'InhabitedTime < "10 minutes" AND Timestamp < "994816000" '
                                     'AND Circle !contains "0;0;16"')

    def test_protect_file_errors_stop_the_prune(self):
        protect = self.world / "protect.txt"
        protect.write_text("overworld 10 20\n")
        with self.assertRaises(SystemExit):
            prune_plan.protected_areas("overworld", protect)

    def test_plan_deletes_only_unkept_candidates(self):
        region_file(self.region / "r.0.0.mca", [0, 1, 2, 3])    # chunks (0,0) .. (3,0)
        region_file(self.region / "r.-1.0.mca", [0])           # chunk (-32,0)
        region_file(self.region / "r.1.0.mca", [5])            # whole region kept
        keep = self.world / "keep.csv"
        keep.write_text("0;0;1;0\n0;0;9;9\n1;0\n")
        # (3,0) is not a candidate (e.g. unreadable), so it stays although not kept.
        candidates = self.world / "candidates.csv"
        candidates.write_text("0;0;0;0\n0;0;1;0\n0;0;2;0\n-1;0\n1;0\n")
        delete = self.world / "delete.csv"
        self.assertEqual(prune_plan.plan(self.world, "overworld", keep, candidates, delete), 0)
        self.assertEqual(delete.read_text().split(), ["-1;0", "0;0;0;0", "0;0;2;0"])

    def test_plan_refuses_to_delete_too_much(self):
        region_file(self.region / "r.0.0.mca", [0, 1])
        keep = self.world / "keep.csv"
        keep.write_text("5;5\n")
        candidates = self.world / "candidates.csv"
        candidates.write_text("0;0\n")
        os.environ["PRUNE_MAX_PERCENT"] = "50"
        self.assertEqual(prune_plan.plan(self.world, "overworld", keep, candidates,
                                         self.world / "d.csv"), 3)

    def test_cli_requires_settings(self):
        env = {key: value for key, value in os.environ.items() if not key.startswith("PRUNE_")}
        result = subprocess.run([sys.executable, str(ROOT / "scripts/prune_plan.py"), "keep",
                                 str(self.world), "overworld"], env=env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PRUNE_", result.stderr)


if __name__ == "__main__":
    unittest.main()
