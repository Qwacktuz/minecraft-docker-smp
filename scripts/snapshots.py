#!/usr/bin/env python3
"""Lists restic snapshots newest first: restic snapshots --json | snapshots.py

Prints "<epoch> <id>" per snapshot. Exits 1 when there are none, or when restic
printed an error instead of JSON.
"""

import json
import re
import sys
from datetime import datetime


def epoch(time):
    """Seconds since the epoch for a restic timestamp (nanoseconds, any offset)."""
    time = re.sub(r"\.\d+", "", time).replace("Z", "+00:00")  # drop fractional seconds
    return int(datetime.fromisoformat(time).timestamp())


def newest_first(snapshots):
    return sorted(((epoch(s["time"]), s["id"]) for s in snapshots), reverse=True)


def main(stdin=sys.stdin, stdout=sys.stdout):
    try:
        snapshots = newest_first(json.load(stdin))
    except ValueError:  # restic printed an error instead of JSON
        return 1
    if not snapshots:
        return 1
    for time, id in snapshots:
        print(time, id, file=stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
