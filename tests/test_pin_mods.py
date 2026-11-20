"""scripts/pin_mods.py with a fake Modrinth API; nothing is fetched."""

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import pin_mods  # noqa: E402

COMPOSE = """services:
  minecraft-service:
    environment:
      TYPE: FABRIC
      VERSION: "26.3"
      MODRINTH_PROJECTS: |
        datapack:skull-portable

        fabric-api
        #fabricexporter # No 26.3 release yet
        c2me-fabric:alpha
        servercore
        balm # soft dependency
        simple-voice-chat:beta
        needs-dep

      RCON_CMDS_STARTUP: |-
        gamerule players_sleeping_percentage 0
"""


def version(project, id, number, kind, date, deps=()):
    return {"project_id": project, "id": id, "version_number": number, "version_type": kind,
            "date_published": date, "dependencies": [
                {"project_id": dep, "version_id": None, "dependency_type": "required"} for dep in deps]}


VERSIONS = {
    "skull-portable": [version("P0", "dp000001", "1.4", "release", "2026-11-01T00:00:00Z")],
    "fabric-api": [version("P1", "fa000002", "0.140.1", "beta", "2026-11-18T00:00:00Z"),
                   version("P1", "fa000001", "0.140.0", "release", "2026-11-10T00:00:00Z")],
    "c2me-fabric": [version("P2", "c2000001", "0.3.5+alpha.1", "alpha", "2026-11-12T00:00:00Z"),
                    version("P2", "c2000000", "0.3.4", "release", "2026-10-12T00:00:00Z")],
    "servercore": [version("P3", "sc000001", "1.5.10", "release", "2026-11-02T00:00:00Z", ["P1"])],
    "balm": [version("P4", "ba000001", "21.0.1", "release", "2026-11-03T00:00:00Z")],
    "simple-voice-chat": [version("P5", "sv000002", "2.6.7-alpha", "alpha", "2026-11-15T00:00:00Z"),
                          version("P5", "sv000001", "2.6.6", "beta", "2026-11-05T00:00:00Z")],
    "needs-dep": [version("P6", "nd000001", "1.0", "release", "2026-11-04T00:00:00Z", ["P9"])],
}


# Modrinth's server_side: P4 (balm) is client-only and unrequired; P1 (fabric-api)
# is marked client-only too, but servercore requires it.
PROJECTS = {
    "P1": {"id": "P1", "slug": "fabric-api", "server_side": "unsupported"},
    "P4": {"id": "P4", "slug": "balm", "server_side": "unsupported"},
    "P3": {"id": "P3", "slug": "servercore", "server_side": "required"},
    "P9": {"id": "P9", "slug": "hidden-lib", "server_side": "required"},
}


class FakeApi:
    def __init__(self):
        self.calls = []

    def __call__(self, path, query=None):
        self.calls.append((path, query))
        if path.startswith(pin_mods.FABRIC_META):
            return [{"loader": {"version": "0.21.0", "stable": False}},
                    {"loader": {"version": "0.20.1", "stable": True}}]
        if path == "projects":
            return [PROJECTS[id] for id in json.loads(query["ids"]) if id in PROJECTS]
        return VERSIONS.get(path.split("/")[1], [])


class PinModsTests(unittest.TestCase):
    def run_pin(self, text=COMPOSE, *argv):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        compose = Path(temp.name) / "compose.yml"
        compose.write_text(text)
        api, out, err = FakeApi(), io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = pin_mods.main(["--compose", str(compose), *argv], fetch=api)
        return code, compose.read_text(), out.getvalue(), err.getvalue(), api

    def test_pins_newest_allowed_version_with_a_comment(self):
        code, text, _, err, api = self.run_pin(COMPOSE, "--write")
        self.assertEqual(code, 0, err)
        for line in ("        datapack:skull-portable:dp000001 # 1.4\n",
                     "        fabric-api:fa000001 # 0.140.0\n",  # the newer beta isn't allowed
                     "        c2me-fabric:c2000001 # 0.3.5+alpha.1 [alpha]\n",
                     "        servercore:sc000001 # 1.5.10\n",
                     "        balm:ba000001 # 21.0.1 (soft dependency)\n",
                     "        simple-voice-chat:sv000001 # 2.6.6 [beta]\n"):  # alpha isn't allowed
            self.assertIn(line, text)
        # Untouched: comments, blank lines, other keys.
        self.assertIn("        #fabricexporter # No 26.3 release yet\n", text)
        self.assertIn("        gamerule players_sleeping_percentage 0\n", text)
        loaders = {path: json.loads(query["loaders"]) for path, query in api.calls if query and "loaders" in query}
        self.assertEqual(loaders["project/skull-portable/version"], ["datapack"])
        self.assertEqual(loaders["project/fabric-api/version"], ["fabric"])
        self.assertEqual(json.loads(api.calls[0][1]["game_versions"]), ["26.3"])

    def test_rerun_keeps_type_and_note_and_updates(self):
        _, text, _, _, _ = self.run_pin(COMPOSE, "--write")
        VERSIONS["c2me-fabric"].insert(0, version("P2", "c2000002", "0.3.6+alpha.0", "alpha",
                                                  "2026-11-19T00:00:00Z"))
        self.addCleanup(VERSIONS["c2me-fabric"].pop, 0)
        code, again, _, _, _ = self.run_pin(text, "--write")
        self.assertEqual(code, 0)
        self.assertIn("        c2me-fabric:c2000002 # 0.3.6+alpha.0 [alpha]\n", again)
        self.assertIn("        balm:ba000001 # 21.0.1 (soft dependency)\n", again)
        self.assertEqual(again.count("\n"), text.count("\n"))

    def test_reports_unlisted_dependencies_and_missing_versions(self):
        code, text, _, err, _ = self.run_pin(COMPOSE + "", "--write")
        self.assertIn("hidden-lib is a required dependency of needs-dep", err)
        self.assertNotIn("fabric-api is a required", err)  # listed explicitly
        missing = COMPOSE.replace("        balm # soft dependency\n", "        gone-mod\n")
        code, text, _, err, _ = self.run_pin(missing, "--write")
        self.assertEqual(code, 1)
        self.assertIn("gone-mod: no release-or-better fabric version", err)
        self.assertIn("        gone-mod\n", text)

    def test_notes_client_only_mods_that_nothing_requires(self):
        code, _, _, err, _ = self.run_pin(COMPOSE, "--write")
        self.assertEqual(code, 0, err)  # a note never fails the run
        self.assertIn("note: balm is client-only on Modrinth", err)
        self.assertNotIn("note: fabric-api", err)  # servercore requires it
        self.assertNotIn("note: servercore", err)
        self.assertNotIn("note: hidden-lib", err)  # reported as missing instead
        quiet = COMPOSE.replace("balm # soft dependency", "balm # (works on the server)")
        _, _, _, err, _ = self.run_pin(quiet, "--write")
        self.assertNotIn("note: balm", err)

    def test_dry_run_prints_changes_only(self):
        code, text, out, _, _ = self.run_pin(COMPOSE)
        self.assertEqual(text, COMPOSE)
        self.assertIn("fabric-api:fa000001 # 0.140.0", out)
        self.assertNotIn("fabricexporter", out)

    def test_pins_stable_loader_for_compose_game_version(self):
        code, text, _, _, api = self.run_pin(COMPOSE, "--write")
        self.assertIn('      TYPE: FABRIC\n      FABRIC_LOADER_VERSION: "0.20.1"\n', text)
        self.assertIn((f"{pin_mods.FABRIC_META}/26.3", None), api.calls)
        _, again, _, _, _ = self.run_pin(text, "--write")
        self.assertEqual(again.count("FABRIC_LOADER_VERSION"), 1)

    def test_real_compose_entries_all_parse(self):
        lines = (ROOT / "compose.yml").read_text().splitlines(keepends=True)
        start = next(i for i, line in enumerate(lines) if "MODRINTH_PROJECTS: |" in line)
        parsed = []
        for line in lines[start + 1:]:
            if line.strip() and not line.startswith(" " * 8):
                break
            entry = pin_mods.parse(line)
            if entry:
                parsed.append(entry)
        slugs = {entry[2]: entry[3] for entry in parsed}
        self.assertGreater(len(slugs), 20)
        self.assertEqual((slugs["c2me-fabric"], slugs["simple-voice-chat"], slugs["lithium"]),
                         ("alpha", "beta", "release"))


if __name__ == "__main__":
    unittest.main()
