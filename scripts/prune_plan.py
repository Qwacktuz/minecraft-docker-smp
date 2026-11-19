#!/usr/bin/env python3
"""Plans a chunk prune for scripts/prune.sh. Standard library only.

  prune_plan.py keep <world> <dimension>
      Print the MCA Selector query for the chunks to KEEP (prune.sh widens that
      selection by PRUNE_BUFFER chunks).
  prune_plan.py candidates <world> <dimension>
      Print the query for chunks that fail every keep rule.
  prune_plan.py plan <world> <dimension> <keep.csv> <candidates.csv> <delete.csv>
      Write the candidates outside the widened keep selection to <delete.csv>
      (MCA Selector selection format) and print a one-line summary.

A chunk is deleted only when MCA Selector read it and matched it as a candidate.
A chunk it can't read is never deleted.

A chunk is kept when ANY of these holds (prune.sh then adds PRUNE_BUFFER chunks
around every kept chunk):
  - players spent at least PRUNE_MIN_INHABITED in it,
  - it was saved in the last PRUNE_UNTOUCHED_DAYS days,
  - it is within PRUNE_PLAYER_RADIUS chunks of a player's position or respawn point,
  - it is inside an area listed in prune/protect.txt.
"""

import gzip
import math
import os
import struct
import sys
import time
from pathlib import Path

DIMENSIONS = ("overworld", "the_nether", "the_end")


def setting(name):
    value = os.environ.get(name)
    if not value:
        sys.exit(f"prune_plan: {name} is not set (see prune/settings.env)")
    return value


# --- Minimal NBT reader (player files) ------------------------------------------

def read_nbt(data):
    """Parses an uncompressed NBT blob and returns the root compound as a dict."""
    pos = 0

    def take(n):
        nonlocal pos
        chunk = data[pos:pos + n]
        pos += n
        return chunk

    def unpack(fmt):
        return struct.unpack(">" + fmt, take(struct.calcsize(">" + fmt)))[0]

    def string():
        return take(unpack("H")).decode("utf-8", "replace")

    def payload(tag):
        if tag == 1: return unpack("b")
        if tag == 2: return unpack("h")
        if tag == 3: return unpack("i")
        if tag == 4: return unpack("q")
        if tag == 5: return unpack("f")
        if tag == 6: return unpack("d")
        if tag == 7: return take(unpack("i"))
        if tag == 8: return string()
        if tag == 9:
            kind, length = unpack("b"), unpack("i")
            return [payload(kind) for _ in range(length)]
        if tag == 10:
            result = {}
            while (kind := unpack("b")) != 0:
                name = string()
                result[name] = payload(kind)
            return result
        if tag == 11: return [unpack("i") for _ in range(unpack("i"))]
        if tag == 12: return [unpack("q") for _ in range(unpack("i"))]
        raise ValueError(f"unknown NBT tag {tag}")

    if unpack("b") != 10:
        raise ValueError("root is not a compound")
    string()
    return payload(10)


def dimension_id(dimension):
    return f"minecraft:{dimension}"


def player_points(world, dimension):
    """Block (x, z) of every player's position and respawn point in a dimension."""
    points = []
    folder = Path(world) / "players/data"
    for path in sorted(folder.glob("*.dat")):
        try:
            player = read_nbt(gzip.decompress(path.read_bytes()))
        except (OSError, ValueError, struct.error, EOFError) as error:
            print(f"prune_plan: skipping unreadable {path.name}: {error}", file=sys.stderr)
            continue
        if player.get("Dimension") == dimension_id(dimension) and len(player.get("Pos", [])) == 3:
            points.append((player["Pos"][0], player["Pos"][2]))
        # Respawn point: `respawn` compound since 1.21.5, SpawnX/Z before.
        respawn = player.get("respawn")
        if isinstance(respawn, dict) and respawn.get("dimension", dimension_id("overworld")) == dimension_id(dimension):
            if len(respawn.get("pos", [])) == 3:
                points.append((respawn["pos"][0], respawn["pos"][2]))
        elif "SpawnX" in player and player.get("SpawnDimension", dimension_id("overworld")) == dimension_id(dimension):
            points.append((player["SpawnX"], player["SpawnZ"]))
    return points


def protected_areas(dimension, path):
    """(x, z, radius) in blocks from protect.txt lines: `<dimension> <x> <z> <radius>`."""
    areas = []
    if not path or not Path(path).exists():
        return areas
    for number, line in enumerate(Path(path).read_text().splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) != 4 or fields[0] not in DIMENSIONS:
            sys.exit(f"prune_plan: {path}:{number}: expected '<dimension> <x> <z> <radius>', "
                     f"dimension one of {', '.join(DIMENSIONS)}")
        if fields[0] == dimension:
            areas.append(tuple(int(value) for value in fields[1:]))
    return areas


def circles(world, dimension, protect_file):
    """MCA Selector circles (chunk x;z;radius) around players and protected areas."""
    player_radius = int(setting("PRUNE_PLAYER_RADIUS"))
    result = [(math.floor(x / 16), math.floor(z / 16), player_radius)
              for x, z in player_points(world, dimension)]
    result += [(math.floor(x / 16), math.floor(z / 16), math.ceil(radius / 16))
               for x, z, radius in protected_areas(dimension, protect_file)]
    return sorted(set(result))


def query(kind, world, dimension, protect_file, now=None):
    """The keep query (any rule holds) or the candidates query (every rule fails)."""
    now = time.time() if now is None else now
    cutoff = int(now - float(setting("PRUNE_UNTOUCHED_DAYS")) * 86400)
    keep = kind == "keep"
    parts = [f'InhabitedTime {">=" if keep else "<"} "{setting("PRUNE_MIN_INHABITED")}"',
             f'Timestamp {">=" if keep else "<"} "{cutoff}"']
    rings = circles(world, dimension, protect_file)
    if rings:
        parts.append(f'Circle {"contains" if keep else "!contains"} "'
                     + ",".join(f"{x};{z};{r}" for x, z, r in rings) + '"')
    return (" OR " if keep else " AND ").join(parts)


# --- Selections -----------------------------------------------------------------

def existing_chunks(region_dir):
    """{(region_x, region_z): set of absolute chunk (x, z)} from .mca headers."""
    regions = {}
    for path in Path(region_dir).glob("r.*.*.mca"):
        _, rx, rz, _ = path.name.split(".")
        rx, rz = int(rx), int(rz)
        with path.open("rb") as handle:
            header = handle.read(4096)
        if len(header) < 4096:
            continue
        chunks = set()
        for index in range(1024):
            if struct.unpack_from(">I", header, index * 4)[0] >> 8:
                chunks.add((rx * 32 + index % 32, rz * 32 + index // 32))
        if chunks:
            regions[(rx, rz)] = chunks
    return regions


def read_selection(path):
    """(whole regions, single chunks) from an MCA Selector CSV. MCA Selector
    writes no file for an empty selection."""
    whole, single = set(), set()
    lines = Path(path).read_text().split() if Path(path).exists() else []
    if lines[:1] == ["inverted"]:
        sys.exit("prune_plan: inverted keep selections are not supported")
    for line in lines:
        values = [int(value) for value in line.split(";")]
        if len(values) == 2:
            whole.add(tuple(values))
        elif len(values) == 4:
            single.add((values[2], values[3]))
        else:
            sys.exit(f"prune_plan: unexpected selection line {line!r}")
    return whole, single


def plan(world, dimension, keep_csv, candidates_csv, delete_csv):
    region_dir = Path(world) / "dimensions/minecraft" / dimension / "region"
    regions = existing_chunks(region_dir)
    kept_regions, kept_chunks = read_selection(keep_csv)
    candidate_regions, candidate_chunks = read_selection(candidates_csv)
    total = deleted = emptied = 0
    lines = []
    for region in sorted(regions):
        chunks = regions[region]
        total += len(chunks)
        if region in kept_regions:
            continue
        candidates = chunks if region in candidate_regions else chunks & candidate_chunks
        doomed = sorted(candidates - kept_chunks)
        deleted += len(doomed)
        if len(doomed) == len(chunks):
            emptied += 1
            lines.append(f"{region[0]};{region[1]}")
        else:
            lines += [f"{region[0]};{region[1]};{x};{z}" for x, z in doomed]
    Path(delete_csv).write_text("".join(line + "\n" for line in lines))
    percent = 100 * deleted / total if total else 0
    print(f"{dimension}: {deleted} of {total} chunks to delete ({percent:.1f}%), "
          f"{emptied} region files removed entirely")
    if percent > float(setting("PRUNE_MAX_PERCENT")):
        print(f"prune_plan: {dimension} would lose more than PRUNE_MAX_PERCENT="
              f"{setting('PRUNE_MAX_PERCENT')}% of its chunks; refusing", file=sys.stderr)
        return 3
    return 0


def main(argv):
    if len(argv) == 3 and argv[0] in ("keep", "candidates") and argv[2] in DIMENSIONS:
        print(query(argv[0], argv[1], argv[2], os.environ.get("PRUNE_PROTECT")))
        return 0
    if len(argv) == 6 and argv[0] == "plan" and argv[2] in DIMENSIONS:
        return plan(*argv[1:])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
