#!/usr/bin/env python3
"""Pins every MODRINTH_PROJECTS entry in compose.yml to a Modrinth version ID.

    python3 scripts/pin_mods.py [--write] [--game-version 26.3]

Run it on the laptop (it needs api.modrinth.com). Without --write it prints
the new lines; with --write it rewrites compose.yml. For each active entry it
picks the newest version for the game version and loader (fabric, or datapack
for `datapack:` entries) whose type is allowed: release, or what a `:beta` /
`:alpha` suffix allows. Pinned lines look like

    c2me-fabric:AbCdEf12 # 0.3.5+alpha.1 [alpha]

The comment keeps the human version and, in brackets, the allowed type, so a
later run (to update the pins) still allows alpha versions. Commented-out
entries are left alone. Required dependencies that aren't listed are reported:
itzg pulls them in (MODRINTH_DOWNLOAD_DEPENDENCIES), unpinned, so add them.
"""

import argparse
import json
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request

API = "https://api.modrinth.com/v2"
COMPOSE = Path(__file__).resolve().parents[1] / "compose.yml"
TYPES = ("release", "beta", "alpha")  # most stable first
ENTRY = re.compile(
    r"^(?P<indent>\s*)(?P<prefix>datapack:)?(?P<slug>[a-z0-9_.-]+)"
    r"(?::(?P<version>[A-Za-z0-9.+_-]+))?\s*(?:#\s*(?P<comment>.*))?$")
ALLOWED = re.compile(r"\[(alpha|beta|release)\]")


def get(path, query=None, opener=urllib.request.urlopen):
    url = f"{API}/{path}" + ("?" + urllib.parse.urlencode(query) if query else "")
    request = urllib.request.Request(url, headers={"User-Agent": "minecraft-docker-smp pin_mods.py"})
    with opener(request, timeout=30) as response:
        return json.load(response)


def parse(line):
    """(indent, prefix, slug, allowed type, note) for an active entry, else None."""
    if not line.strip() or line.lstrip().startswith("#"):
        return None
    match = ENTRY.match(line.rstrip("\n"))
    if not match:
        raise ValueError(f"can't read MODRINTH_PROJECTS line: {line.strip()!r}")
    version, comment = match["version"], match["comment"] or ""
    allowed = "release"
    if version in TYPES:
        allowed = version
    elif (found := ALLOWED.search(comment)):
        allowed = found[1]
    # Drop what a previous run wrote (version and [type]); keep the owner's note.
    note = ALLOWED.sub("", comment)
    if version not in (None, *TYPES):
        note = re.sub(r"^\S+\s*", "", note)  # the human version number
    note = note.strip().strip("()").strip()
    return match["indent"], match["prefix"] or "", match["slug"], allowed, note


def newest(versions, allowed):
    """The newest version whose type is allowed (allowed or more stable)."""
    ok = TYPES[:TYPES.index(allowed) + 1]
    candidates = [v for v in versions if v["version_type"] in ok]
    return max(candidates, key=lambda v: v["date_published"], default=None)


def pin(lines, game_version, fetch=get):
    """Returns (new lines, problems, required project IDs not listed)."""
    block, out, problems, listed, needed = False, [], [], set(), {}
    for line in lines:
        if re.match(r"^\s*MODRINTH_PROJECTS:\s*\|", line):
            block = True
            out.append(line)
            continue
        if block and line.strip() and not line.startswith(" " * 8):
            block = False
        entry = parse(line) if block else None
        if entry is None:
            out.append(line)
            continue
        indent, prefix, slug, allowed, note = entry
        loader = "datapack" if prefix else "fabric"
        versions = fetch(f"project/{slug}/version", {
            "game_versions": json.dumps([game_version]), "loaders": json.dumps([loader])})
        chosen = newest(versions, allowed)
        if chosen is None:
            problems.append(f"{slug}: no {allowed}-or-better {loader} version for {game_version}; left as is")
            out.append(line)
            continue
        listed.add(chosen["project_id"])
        for dependency in chosen.get("dependencies", []):
            if dependency.get("dependency_type") == "required" and dependency.get("project_id"):
                needed.setdefault(dependency["project_id"], slug)
        tag = f" [{allowed}]" if allowed != "release" else ""
        extra = f" ({note})" if note else ""
        out.append(f"{indent}{prefix}{slug}:{chosen['id']} # {chosen['version_number']}{tag}{extra}\n")
    missing = {project: by for project, by in needed.items() if project not in listed}
    return out, problems, missing


def main(argv=None, fetch=get):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", action="store_true", help="rewrite compose.yml")
    parser.add_argument("--game-version", default="26.3")
    parser.add_argument("--compose", type=Path, default=COMPOSE)
    args = parser.parse_args(argv)
    lines = args.compose.read_text().splitlines(keepends=True)
    out, problems, missing = pin(lines, args.game_version, fetch)
    for problem in problems:
        print(f"warning: {problem}", file=sys.stderr)
    if missing:
        projects = fetch("projects", {"ids": json.dumps(sorted(missing))})
        for project in projects:
            print(f"warning: {project['slug']} is a required dependency of {missing[project['id']]} "
                  "but not listed; itzg downloads it unpinned. Add it and run again.", file=sys.stderr)
    if args.write:
        args.compose.write_text("".join(out))
    else:
        sys.stdout.writelines(new for old, new in zip(lines, out) if old != new)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
