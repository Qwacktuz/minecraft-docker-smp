import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import leaderboard  # noqa: E402

ALICE = "069a79f4-44e9-4726-a5be-fca90e38aaf5"
BOB = "853c80ef-3c37-49fd-aa49-938b674adae6"
BOT = "11111111-2222-3333-4444-555555555555"  # a Carpet bot: not whitelisted


def stats(play_ticks=0, mined=None, **custom):
    values = {"minecraft:play_time": play_ticks, **{f"minecraft:{k}": v for k, v in custom.items()}}
    return {"stats": {"minecraft:custom": values, "minecraft:mined": mined or {}}, "DataVersion": 4000}


def ledger_db(path, actions, uuid_as_text=False):
    """A database with Ledger 1.3.25's tables (the columns this script reads)."""
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE ActionIdentifiers (id INTEGER PRIMARY KEY, action_identifier VARCHAR(16));
        CREATE TABLE players (id INTEGER PRIMARY KEY, player_id BLOB, player_name VARCHAR(16),
                              first_join TEXT, last_join TEXT);
        CREATE TABLE actions (id INTEGER PRIMARY KEY, action_id INT, time TEXT, x INT, y INT, z INT,
                              world_id INT, object_id INT, old_object_id INT, block_state TEXT,
                              old_block_state TEXT, source INT, player_id INT, extra_data TEXT,
                              rolled_back BOOLEAN DEFAULT 0);
        INSERT INTO ActionIdentifiers VALUES (1, 'block-place'), (2, 'block-break');
    """)
    for number, (player_uuid, name) in enumerate([(ALICE, "Alice"), (BOB, "bob_new")], start=1):
        stored = player_uuid if uuid_as_text else uuid.UUID(player_uuid).bytes
        db.execute("INSERT INTO players (id, player_id, player_name) VALUES (?, ?, ?)", (number, stored, name))
    for action, player, rolled_back in actions:
        db.execute("INSERT INTO actions (action_id, player_id, rolled_back) VALUES (?, ?, ?)",
                   (action, player, rolled_back))
    db.commit()
    db.close()


class LeaderboardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.world = self.data / "world"
        (self.world / "players/stats").mkdir(parents=True)
        (self.data / "whitelist.json").write_text(json.dumps([{"uuid": ALICE, "name": "Alice"},
                                                              {"uuid": BOB, "name": "bob"}]))
        (self.data / "usercache.json").write_text(json.dumps([{"uuid": BOB, "name": "bob_new",
                                                               "expiresOn": "x"}]))

    def tearDown(self):
        self.tmp.cleanup()

    def write_stats(self, player_uuid, data, folder="players/stats"):
        (self.world / folder).mkdir(parents=True, exist_ok=True)
        (self.world / folder / f"{player_uuid}.json").write_text(json.dumps(data))

    def board(self):
        return {row["name"]: row for row in leaderboard.leaderboard(self.data)["players"]}

    def test_totals_from_the_game_stats(self):
        self.write_stats(ALICE, stats(
            play_ticks=72_000 * 3,  # 3 hours
            walk_one_cm=150_000, sprint_one_cm=250_000, aviate_one_cm=1_000_000, fall_one_cm=0,
            mob_kills=12, deaths=2,
            mined={"minecraft:stone": 300, "minecraft:dirt": 45}))
        alice = self.board()["Alice"]
        self.assertEqual(alice["play_hours"], 3.0)
        self.assertEqual(alice["distance_km"], 14.0)  # 1.5 + 2.5 + 10 km
        self.assertEqual(alice["elytra_km"], 10.0)
        self.assertEqual(alice["mined"], 345)
        self.assertEqual((alice["mob_kills"], alice["deaths"]), (12, 2))
        self.assertNotIn("placed", alice)  # no Ledger database

    def test_bots_and_players_off_the_whitelist_are_left_out(self):
        self.write_stats(ALICE, stats())
        self.write_stats(BOT, stats(play_ticks=10**9))
        self.assertEqual(list(self.board()), ["Alice"])

    def test_ops_count_even_when_not_whitelisted(self):
        (self.data / "ops.json").write_text(json.dumps([{"uuid": BOT, "name": "carol", "level": 4}]))
        self.write_stats(BOT, stats())
        self.assertIn("carol", self.board())

    def test_the_newest_name_wins(self):
        self.write_stats(BOB, stats())
        self.assertIn("bob_new", self.board())  # from usercache.json, not the whitelist

    def test_older_stats_folder(self):
        self.write_stats(ALICE, stats(play_ticks=72_000), folder="stats")
        self.assertEqual(self.board()["Alice"]["play_hours"], 1.0)

    def test_blocks_placed_from_ledger_without_rolled_back_ones(self):
        self.write_stats(ALICE, stats())
        self.write_stats(BOB, stats())
        ledger_db(self.world / "ledger.sqlite", [
            (1, 1, 0), (1, 1, 0), (1, 1, 1),  # Alice: 2 placed, 1 rolled back
            (2, 1, 0),                        # Alice broke a block: not counted
        ])
        board = self.board()
        self.assertEqual(board["Alice"]["placed"], 2)
        self.assertEqual(board["bob_new"]["placed"], 0)

    def test_ledger_uuids_stored_as_text(self):
        self.write_stats(ALICE, stats())
        ledger_db(self.world / "ledger.sqlite", [(1, 1, 0)], uuid_as_text=True)
        self.assertEqual(self.board()["Alice"]["placed"], 1)

    def test_an_unexpected_ledger_database_keeps_the_rest(self):
        self.write_stats(ALICE, stats(play_ticks=72_000))
        sqlite3.connect(self.world / "ledger.sqlite").execute("CREATE TABLE other (x)").connection.close()
        alice = self.board()["Alice"]
        self.assertEqual(alice["play_hours"], 1.0)
        self.assertNotIn("placed", alice)

    def test_command_line(self):
        self.write_stats(ALICE, stats())
        result = subprocess.run([sys.executable, ROOT / "scripts/leaderboard.py", self.data],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([p["name"] for p in json.loads(result.stdout)["players"]], ["Alice"])
        missing = subprocess.run([sys.executable, ROOT / "scripts/leaderboard.py", self.data / "nope"],
                                 capture_output=True, text=True)
        self.assertEqual(missing.returncode, 1)


if __name__ == "__main__":
    unittest.main()
