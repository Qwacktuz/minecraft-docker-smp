"""scripts/snapshots.py: restic snapshot JSON to "<epoch> <id>", newest first."""

import io
import json
from pathlib import Path
import subprocess
import sys
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/snapshots.py"
sys.path.insert(0, str(SCRIPT.parent))
import snapshots  # noqa: E402


def run(text):
    out = io.StringIO()
    return snapshots.main(io.StringIO(text), out), out.getvalue()


class SnapshotsTests(unittest.TestCase):
    def test_nanoseconds_and_offsets(self):
        # 2026-11-19T12:00:00Z, written three ways.
        for time in ("2026-11-19T12:00:00Z", "2026-11-19T12:00:00.123456789Z",
                     "2026-11-19T13:00:00.123456789+01:00"):
            with self.subTest(time=time):
                self.assertEqual(snapshots.epoch(time), 1795089600)

    def test_newest_first(self):
        snaps = [{"id": "old", "time": "2026-11-17T12:00:00Z"},
                 {"id": "new", "time": "2026-11-19T12:00:00.5+01:00"},
                 {"id": "mid", "time": "2026-11-18T12:00:00.999999999-05:00"}]
        code, out = run(json.dumps(snaps))
        self.assertEqual(code, 0)
        self.assertEqual([line.split()[1] for line in out.splitlines()], ["new", "mid", "old"])
        self.assertEqual(out.splitlines()[0], "1795086000 new")

    def test_invalid_json_and_no_snapshots_fail(self):
        for text in ("Fatal: unable to open repository", "", "[]"):
            with self.subTest(text=text):
                self.assertEqual(run(text), (1, ""))

    def test_command_line(self):
        snaps = json.dumps([{"id": "abc", "time": "2026-11-19T12:00:00Z"}])
        result = subprocess.run([sys.executable, str(SCRIPT)], input=snaps, capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout), (0, "1795089600 abc\n"))
        result = subprocess.run([sys.executable, str(SCRIPT)], input="not json", capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (1, "", ""))


if __name__ == "__main__":
    unittest.main()
