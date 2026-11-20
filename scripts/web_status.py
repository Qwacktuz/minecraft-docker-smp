#!/usr/bin/env python3
"""JSON for the web app (web/), written on the VPS by scripts/publish-status.sh.

    web_status.py vps <type> <location> <ipv4>

Prints vps.json: the Hetzner server type and location (from bin/server's
OpenTofu outputs), the IPv4 address (the web app shows the hardware only while
DNS points at this address), and what the machine has: vCPUs, CPU model, RAM,
disk, and the game's heap (MEMORY in compose.yml).

    web_status.py players <data dir>

Prints players.json: the whitelist with op flags, from whitelist.json and
ops.json in the game's data folder. Exits 1 when there is no whitelist.json yet
(nothing to publish, so the last published list stays).
"""

import json
import os
import platform
import re
import shutil
import sys
from pathlib import Path
from time import time as unix_now


def read_cpu_model(cpuinfo="/proc/cpuinfo"):
    """The first "model name" in /proc/cpuinfo, or None (e.g. on ARM)."""
    try:
        for line in Path(cpuinfo).read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return None


def read_memory_bytes(meminfo="/proc/meminfo"):
    for line in Path(meminfo).read_text().splitlines():
        if line.startswith("MemTotal:"):
            return int(line.split()[1]) * 1024  # kB
    raise ValueError("no MemTotal in " + meminfo)


def read_heap(compose="compose.yml"):
    """MEMORY for the game container ("5G"), or None."""
    try:
        match = re.search(r'^\s+MEMORY:\s*"?([0-9]+[MG])"?\s*$', Path(compose).read_text(), re.M)
    except OSError:
        return None
    return match.group(1) if match else None


def vps(server_type, location, ipv4, root="."):
    return {
        "updated": int(unix_now()),
        "type": server_type,
        "location": location,
        "ipv4": ipv4,
        "arch": platform.machine(),
        "cpus": os.cpu_count(),
        "cpu_model": read_cpu_model(),
        "memory_bytes": read_memory_bytes(),
        "disk_bytes": shutil.disk_usage(root).total,
        "heap": read_heap(Path(root) / "compose.yml"),
    }


def players(data_dir):
    data = Path(data_dir)
    whitelist = json.loads((data / "whitelist.json").read_text())
    try:
        ops = json.loads((data / "ops.json").read_text())
    except FileNotFoundError:
        ops = []
    levels = {op["uuid"]: op.get("level", 4) for op in ops}
    entries = {entry["uuid"]: {"name": entry["name"], "uuid": entry["uuid"]} for entry in whitelist}
    # Ops who aren't whitelisted can't join with ENFORCE_WHITELIST, but list them anyway.
    for op in ops:
        entries.setdefault(op["uuid"], {"name": op["name"], "uuid": op["uuid"]})
    for uuid, entry in entries.items():
        entry["whitelisted"] = any(e["uuid"] == uuid for e in whitelist)
        entry["op_level"] = levels.get(uuid)
    listed = sorted(entries.values(), key=lambda e: e["name"].lower())
    return {"updated": int(unix_now()), "players": listed}


def main(argv):
    if len(argv) == 5 and argv[1] == "vps":
        print(json.dumps(vps(*argv[2:5])))
    elif len(argv) == 3 and argv[1] == "players":
        try:
            print(json.dumps(players(argv[2])))
        except FileNotFoundError as missing:
            print(f"web_status: {missing.filename} not found", file=sys.stderr)
            return 1
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
