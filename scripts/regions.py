#!/usr/bin/env python3
"""Region files around a block position, for `bin/server restore --region`.

    regions.py <dimension> <x> <z> [radius]

Prints the path (relative to data/minecraft) of every region file that holds a
block of the square from (x - radius, z - radius) to (x + radius, z + radius),
one per line. The dimension is overworld, nether or end (the_nether, the_end
and minecraft:... work too). x and z are block coordinates, as on the F3
screen; radius is in blocks (default 0: just the region holding x, z).

A region file holds 32 x 32 chunks = 512 x 512 blocks: block x is in region
floor(x / 512), so block -1 is in region -1 and block 511 in region 0.
Folders match scripts/prune.sh: world/dimensions/minecraft/<dimension>/region.
"""

import sys

WORLD = "world"  # compose.yml LEVEL
REGION_BLOCKS = 512
DIMENSIONS = {
    "overworld": "overworld",
    "nether": "the_nether",
    "the_nether": "the_nether",
    "end": "the_end",
    "the_end": "the_end",
}
MAX_RADIUS = 30_000_000  # the world border


def dimension_folder(name):
    folder = DIMENSIONS.get(name.lower().removeprefix("minecraft:"))
    if folder is None:
        raise ValueError(f"unknown dimension '{name}'; use overworld, nether or end")
    return folder


def region(block):
    """The region index holding a block coordinate (floor division)."""
    return block // REGION_BLOCKS


def region_files(dimension, x, z, radius=0):
    if radius < 0 or radius > MAX_RADIUS:
        raise ValueError(f"radius must be between 0 and {MAX_RADIUS} blocks")
    folder = f"{WORLD}/dimensions/minecraft/{dimension_folder(dimension)}/region"
    return [f"{folder}/r.{rx}.{rz}.mca"
            for rx in range(region(x - radius), region(x + radius) + 1)
            for rz in range(region(z - radius), region(z + radius) + 1)]


def main(argv, stdout=sys.stdout, stderr=sys.stderr):
    if len(argv) not in (3, 4):
        print(__doc__.strip(), file=stderr)
        return 2
    try:
        dimension, numbers = argv[0], [int(value) for value in argv[1:]]
        paths = region_files(dimension, *numbers)
    except ValueError as error:
        message = str(error) if "dimension" in str(error) or "radius" in str(error) else \
            "x, z and radius must be whole numbers of blocks"
        print(f"regions.py: {message}", file=stderr)
        return 2
    for path in paths:
        print(path, file=stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
