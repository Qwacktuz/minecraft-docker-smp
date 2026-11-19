#!/usr/bin/env python3
"""Zips a world folder for download: world_zip.py <world-dir> <out.zip>

Leaves out player data (players/: inventories, positions, stats, advancements)
and the session lock. Region files are already compressed, so they are stored.
The zip holds a top-level `world/` folder and a README.txt.
"""

import sys
import time
import zipfile
from pathlib import Path

SKIP_DIRS = {"players"}
SKIP_FILES = {"session.lock"}

README = """\
A copy of the SMP world (Minecraft 26.3, Fabric), made {date} UTC.

Player data is not included: you start at spawn with an empty inventory.
Singleplayer: move `world` into your .minecraft/saves folder.
A local server: put `world` next to the server jar (level-name=world).
The server's mods are listed in compose.yml (MODRINTH_PROJECTS); the world opens
without them, but mod-specific blocks and data need the same mods.
"""


def included(path, world):
    relative = path.relative_to(world)
    return (relative.parts[0] not in SKIP_DIRS and path.name not in SKIP_FILES
            and path.is_file())


def main(world, out):
    world, out = Path(world), Path(out)
    if not (world / "level.dat").is_file():
        sys.exit(f"world_zip: no level.dat in {world}")
    files = sorted(p for p in world.rglob("*") if included(p, world))
    with zipfile.ZipFile(out, "w", allowZip64=True) as archive:
        archive.writestr("README.txt", README.format(date=time.strftime("%Y-%m-%d %H:%M", time.gmtime())),
                         compress_type=zipfile.ZIP_DEFLATED)
        for path in files:
            method = zipfile.ZIP_STORED if path.suffix == ".mca" else zipfile.ZIP_DEFLATED
            archive.write(path, Path("world") / path.relative_to(world), compress_type=method)
    print(f"world_zip: {len(files)} files, {out.stat().st_size / 2**30:.2f} GiB")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])
