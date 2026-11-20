#!/usr/bin/env python3
"""Lists restic snapshots newest first: restic snapshots --json | snapshots.py

Prints "<epoch> <id>" per snapshot. Exits 1 when there are none, or when restic
printed an error instead of JSON.

    restic snapshots --json | snapshots.py --find <id-prefix|latest>

Prints the full ID of the one snapshot whose ID starts with the prefix (or the
newest one). Exits 1 when none or several match.

    restic snapshots --json | snapshots.py --json

Prints {"updated": <epoch>, "snapshots": [{"id", "time", "tags"}, ...]}, newest
first: backups.json for the web app (scripts/publish-status.sh).
"""

import json
import re
import sys
from time import time as unix_now
from datetime import datetime


def epoch(time):
    """Seconds since the epoch for a restic timestamp (nanoseconds, any offset)."""
    time = re.sub(r"\.\d+", "", time).replace("Z", "+00:00")  # drop fractional seconds
    return int(datetime.fromisoformat(time).timestamp())


def newest_first(snapshots):
    return sorted(((epoch(s["time"]), s["id"]) for s in snapshots), reverse=True)


def find(snapshots, wanted):
    """The full ID for an ID prefix or "latest", or None unless exactly one matches."""
    if wanted == "latest":
        return newest_first(snapshots)[0][1] if snapshots else None
    if not re.fullmatch(r"[0-9a-f]{1,64}", wanted):
        return None
    matches = {s["id"] for s in snapshots if s["id"].startswith(wanted)}
    return matches.pop() if len(matches) == 1 else None


def summary(snapshots, now):
    """The web app's backups.json: IDs, times and tags, newest first."""
    rows = sorted(({"id": s["id"], "time": epoch(s["time"]), "tags": s.get("tags") or []} for s in snapshots),
                  key=lambda row: row["time"], reverse=True)
    return {"updated": now, "snapshots": rows}


def main(stdin=sys.stdin, stdout=sys.stdout, argv=(), now=None):
    try:
        data = json.load(stdin)
        if len(argv) == 2 and argv[0] == "--find":
            found = find(data, argv[1])
            if found is None:
                return 1
            print(found, file=stdout)
            return 0
        if list(argv) == ["--json"]:
            json.dump(summary(data, int(unix_now()) if now is None else now), stdout)
            print(file=stdout)
            return 0
        if argv:
            print(__doc__.strip(), file=sys.stderr)
            return 2
        snapshots = newest_first(data)
    except (ValueError, TypeError, KeyError, AttributeError):  # restic printed an error instead of JSON
        return 1
    if not snapshots:
        return 1
    for time, id in snapshots:
        print(time, id, file=stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main(argv=sys.argv[1:]))
