"""scripts/world_zip.py: the public world download."""

from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import world_zip  # noqa: E402


class WorldZipTests(unittest.TestCase):
    def test_zip_leaves_out_player_data_and_stores_regions(self):
        with tempfile.TemporaryDirectory() as temp:
            world = Path(temp) / "world"
            region = world / "dimensions/minecraft/overworld/region"
            region.mkdir(parents=True)
            (world / "level.dat").write_bytes(b"level")
            (world / "session.lock").write_bytes(b"lock")
            (region / "r.0.0.mca").write_bytes(b"\0" * 8192)
            (world / "players/data").mkdir(parents=True)
            (world / "players/data/someone.dat").write_bytes(b"inventory")
            for name in ("ledger.sqlite", "ledger.sqlite-wal", "ledger.sqlite-shm"):
                (world / name).write_bytes(b"who broke what")
            out = Path(temp) / "world.zip"
            world_zip.main(world, out)
            with zipfile.ZipFile(out) as archive:
                names = set(archive.namelist())
                self.assertEqual(names, {"README.txt", "world/level.dat",
                                         "world/dimensions/minecraft/overworld/region/r.0.0.mca"})
                info = archive.getinfo("world/dimensions/minecraft/overworld/region/r.0.0.mca")
                self.assertEqual(info.compress_type, zipfile.ZIP_STORED)

    def test_refuses_a_folder_without_a_world(self):
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(SystemExit):
            world_zip.main(temp, Path(temp) / "world.zip")


if __name__ == "__main__":
    unittest.main()
