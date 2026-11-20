import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import web_status  # noqa: E402


class PlayersTest(unittest.TestCase):
    def write(self, folder, name, data):
        (Path(folder) / name).write_text(json.dumps(data))

    def test_whitelist_with_op_levels_sorted_by_name(self):
        with tempfile.TemporaryDirectory() as data:
            self.write(data, "whitelist.json", [{"uuid": "b", "name": "bob"}, {"uuid": "a", "name": "Alice"}])
            self.write(data, "ops.json", [{"uuid": "b", "name": "bob", "level": 4, "bypassesPlayerLimit": False}])
            players = web_status.players(data)["players"]
        self.assertEqual([p["name"] for p in players], ["Alice", "bob"])
        self.assertEqual(players[0], {"name": "Alice", "uuid": "a", "whitelisted": True, "op_level": None})
        self.assertEqual(players[1]["op_level"], 4)

    def test_ops_who_are_not_whitelisted_are_listed_too(self):
        with tempfile.TemporaryDirectory() as data:
            self.write(data, "whitelist.json", [])
            self.write(data, "ops.json", [{"uuid": "c", "name": "carol", "level": 2}])
            players = web_status.players(data)["players"]
        self.assertEqual(players, [{"name": "carol", "uuid": "c", "whitelisted": False, "op_level": 2}])

    def test_missing_ops_file_means_no_ops(self):
        with tempfile.TemporaryDirectory() as data:
            self.write(data, "whitelist.json", [{"uuid": "a", "name": "alice"}])
            self.assertIsNone(web_status.players(data)["players"][0]["op_level"])

    def test_no_whitelist_exits_1_without_output(self):
        with tempfile.TemporaryDirectory() as data:
            result = subprocess.run([sys.executable, ROOT / "scripts/web_status.py", "players", data],
                                    capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")


class VpsTest(unittest.TestCase):
    def test_describes_this_machine(self):
        info = web_status.vps("cx33", "hel1", "192.0.2.1", root=ROOT)
        self.assertEqual((info["type"], info["location"], info["ipv4"]), ("cx33", "hel1", "192.0.2.1"))
        self.assertGreater(info["cpus"], 0)
        self.assertGreater(info["memory_bytes"], 0)
        self.assertGreater(info["disk_bytes"], 0)
        self.assertEqual(info["heap"], "5G")  # MEMORY in compose.yml

    def test_cpu_model_is_none_without_a_model_name(self):
        with tempfile.NamedTemporaryFile("w", suffix="cpuinfo") as cpuinfo:
            cpuinfo.write("processor\t: 0\nBogoMIPS\t: 50.00\n")
            cpuinfo.flush()
            self.assertIsNone(web_status.read_cpu_model(cpuinfo.name))


if __name__ == "__main__":
    unittest.main()
