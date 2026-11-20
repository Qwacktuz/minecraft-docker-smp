#!/usr/bin/env python3
"""Player totals for the web app's leaderboards: leaderboard.py <data dir>

<data dir> is the game's data folder (data/minecraft): it holds world/,
whitelist.json, ops.json and usercache.json. Prints leaderboard.json:

    {"updated": <epoch>, "players": [{"uuid", "name", <stat>: <number>, ...}]}

Per player, from the game's own stats (world/players/stats/<uuid>.json; older
versions keep them in world/stats/):

- play_hours, distance_km (every way of moving: walking, sprinting, swimming,
  flying, elytra, boats, minecarts, horses...), elytra_km, mined (blocks
  mined), mob_kills, deaths

and from Ledger's log (world/ledger.sqlite), when there is one:

- placed: blocks placed, leaving out placements an op rolled back

Only whitelisted players and ops are listed, so Carpet bots and players who
left the whitelist stay out. Totals only: no positions, inventories or times.
The database is opened read-only, so this is safe while the game runs.
"""

import json
import sqlite3
import sys
import uuid as uuidlib
from pathlib import Path
from time import time as unix_now

CM_PER_KM = 100_000
TICKS_PER_HOUR = 20 * 60 * 60


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def members(data):
    """{uuid: name} of whitelisted players and ops."""
    listed = read_json(data / "whitelist.json", []) + read_json(data / "ops.json", [])
    return {entry["uuid"]: entry["name"] for entry in listed}


def names(data, ledger):
    """The newest known name per UUID: the user cache, then Ledger, then the lists."""
    known = {}
    for entry in read_json(data / "usercache.json", []):
        known.setdefault(entry["uuid"], entry["name"])
    for player_uuid, name in ledger.get("names", {}).items():
        known.setdefault(player_uuid, name)
    return known


def stats_files(world):
    for folder in (world / "players" / "stats", world / "stats"):
        if folder.is_dir():
            yield from sorted(folder.glob("*.json"))


def totals(stats):
    """The leaderboard numbers from one player's stats file."""
    groups = stats.get("stats", {})
    custom = groups.get("minecraft:custom", {})
    play_ticks = custom.get("minecraft:play_time", custom.get("minecraft:play_one_minute", 0))
    distance_cm = sum(value for key, value in custom.items() if key.endswith("_one_cm"))
    return {
        "play_hours": round(play_ticks / TICKS_PER_HOUR, 1),
        "distance_km": round(distance_cm / CM_PER_KM, 2),
        "elytra_km": round(custom.get("minecraft:aviate_one_cm", 0) / CM_PER_KM, 2),
        "mined": sum(groups.get("minecraft:mined", {}).values()),
        "mob_kills": custom.get("minecraft:mob_kills", 0),
        "deaths": custom.get("minecraft:deaths", 0),
    }


def as_uuid(value):
    """Ledger stores UUIDs as 16 bytes (Exposed's uuid column) or, in some
    versions, as text."""
    if isinstance(value, (bytes, bytearray)) and len(value) == 16:
        return str(uuidlib.UUID(bytes=bytes(value)))
    return str(uuidlib.UUID(str(value)))


def ledger_counts(database):
    """{"placed": {uuid: n}, "names": {uuid: name}} from Ledger, or {} without it."""
    if not database.is_file():
        return {}
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        rows = connection.execute("""
            SELECT players.player_id, players.player_name, COUNT(*)
            FROM actions
            JOIN ActionIdentifiers ON ActionIdentifiers.id = actions.action_id
            JOIN players ON players.id = actions.player_id
            WHERE ActionIdentifiers.action_identifier = 'block-place' AND NOT actions.rolled_back
            GROUP BY players.id
        """).fetchall()
        name_rows = connection.execute("SELECT player_id, player_name FROM players").fetchall()
    finally:
        connection.close()
    return {
        "placed": {as_uuid(player_id): count for player_id, _, count in rows},
        "names": {as_uuid(player_id): name for player_id, name in name_rows},
    }


def leaderboard(data_dir):
    data = Path(data_dir)
    world = data / "world"
    listed = members(data)
    try:
        ledger = ledger_counts(world / "ledger.sqlite")
    except (sqlite3.Error, ValueError) as error:
        # A Ledger update could change its tables: keep the rest of the board.
        print(f"leaderboard: could not read Ledger's database ({error}); no blocks placed", file=sys.stderr)
        ledger = {}
    known = names(data, ledger)
    players = []
    for path in stats_files(world):
        player_uuid = path.stem
        if player_uuid not in listed:
            continue
        row = {"uuid": player_uuid, "name": known.get(player_uuid, listed[player_uuid])}
        row.update(totals(json.loads(path.read_text())))
        if "placed" in ledger:
            row["placed"] = ledger["placed"].get(player_uuid, 0)
        players.append(row)
    players.sort(key=lambda row: row["name"].lower())
    return {"updated": int(unix_now()), "players": players}


def main(argv):
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    if not (Path(argv[1]) / "world").is_dir():
        print(f"leaderboard: no world in {argv[1]}", file=sys.stderr)
        return 1
    print(json.dumps(leaderboard(argv[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
