"""scripts/regions.py: block coordinates to region file paths."""

import io
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/regions.py"
sys.path.insert(0, str(SCRIPT.parent))
import regions  # noqa: E402

OVERWORLD = "world/dimensions/minecraft/overworld/region"


def names(paths):
    return [path.rsplit("/", 1)[1] for path in paths]


class RegionTests(unittest.TestCase):
    def test_region_is_floor_of_block_over_512(self):
        cases = {0: 0, 1: 0, 511: 0, 512: 1, 1023: 1, 1024: 2,
                 -1: -1, -511: -1, -512: -1, -513: -2, -1024: -2, -1025: -3,
                 29_999_999: 58_593, -30_000_000: -58_594}
        for block, region in cases.items():
            with self.subTest(block=block):
                self.assertEqual(regions.region(block), region)

    def test_single_region_without_radius(self):
        self.assertEqual(regions.region_files("overworld", 100, -100), [f"{OVERWORLD}/r.0.-1.mca"])
        self.assertEqual(regions.region_files("overworld", -1, -1), [f"{OVERWORLD}/r.-1.-1.mca"])
        self.assertEqual(regions.region_files("overworld", -512, 512), [f"{OVERWORLD}/r.-1.1.mca"])

    def test_radius_edges(self):
        # 511 + 0 stays in region 0; 511 + 1 reaches region 1.
        self.assertEqual(names(regions.region_files("overworld", 511, 0)), ["r.0.0.mca"])
        self.assertEqual(names(regions.region_files("overworld", 511, 0, 1)),
                         ["r.0.-1.mca", "r.0.0.mca", "r.1.-1.mca", "r.1.0.mca"])
        # Block 0 with radius 1 touches -1 on both axes.
        self.assertEqual(len(regions.region_files("overworld", 0, 0, 1)), 4)
        # Block 256 (0..511 is region 0): radius 255 stays inside; 256 reaches block
        # 512 (region 1) but only block 0 on the low side; 257 reaches -1 too.
        self.assertEqual(names(regions.region_files("overworld", 256, 256, 255)), ["r.0.0.mca"])
        self.assertEqual(names(regions.region_files("overworld", 256, 256, 256)),
                         ["r.0.0.mca", "r.0.1.mca", "r.1.0.mca", "r.1.1.mca"])
        self.assertEqual(len(regions.region_files("overworld", 256, 256, 257)), 9)
        # A radius of exactly one region around a corner.
        self.assertEqual(len(regions.region_files("overworld", -512, -512, 512)), 9)

    def test_dimension_folders_match_prune(self):
        expected = {"overworld": "overworld", "nether": "the_nether", "the_nether": "the_nether",
                    "minecraft:the_nether": "the_nether", "end": "the_end", "the_end": "the_end",
                    "END": "the_end"}
        for name, folder in expected.items():
            with self.subTest(name=name):
                self.assertEqual(regions.region_files(name, 0, 0),
                                 [f"world/dimensions/minecraft/{folder}/region/r.0.0.mca"])
        # scripts/prune.sh and prune_plan.py use the same folders.
        prune = (ROOT / "scripts/prune.sh").read_text()
        self.assertIn("dir=dimensions/minecraft/$dim", prune)
        plan = (ROOT / "scripts/prune_plan.py").read_text()
        self.assertIn('DIMENSIONS = ("overworld", "the_nether", "the_end")', plan)
        compose = (ROOT / "compose.yml").read_text()
        self.assertIn(f'LEVEL: "{regions.WORLD}"', compose)

    def test_paths_pass_restore_sh_validation(self):
        restore = (ROOT / "scripts/restore.sh").read_text()
        pattern = re.search(r'\[\[ "\$path" =~ (\S+) \]\]', restore).group(1)
        for path in regions.region_files("end", -700, 700, 600):
            with self.subTest(path=path):
                self.assertRegex(path, pattern)

    def test_bad_input(self):
        for args in (("moon", 0, 0), ("overworld", 0, 0, -1), ("overworld", 0, 0, 30_000_001)):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    regions.region_files(*args)

    def test_command_line(self):
        out, err = io.StringIO(), io.StringIO()
        self.assertEqual(regions.main(["nether", "-1", "-1"], out, err), 0)
        self.assertEqual(out.getvalue(), "world/dimensions/minecraft/the_nether/region/r.-1.-1.mca\n")
        for argv in ([], ["end", "0"], ["end", "x", "0"], ["end", "1.5", "0"], ["moon", "0", "0"],
                     ["end", "0", "0", "-5"], ["end", "0", "0", "1", "2"]):
            with self.subTest(argv=argv):
                err = io.StringIO()
                self.assertEqual(regions.main(argv, io.StringIO(), err), 2)
                self.assertTrue(err.getvalue())
        result = subprocess.run([sys.executable, str(SCRIPT), "end", "512", "-513", "1"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        # x 511..513 -> regions 0, 1; z -514..-512 -> regions -2, -1.
        self.assertEqual(names(result.stdout.split()),
                         ["r.0.-2.mca", "r.0.-1.mca", "r.1.-2.mca", "r.1.-1.mca"])


if __name__ == "__main__":
    unittest.main()
