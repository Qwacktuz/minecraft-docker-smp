#!/usr/bin/env python3
"""Decides whether the VPS should be stopped because nobody is playing.

Run every 15 minutes by .github/workflows/server.yml. It needs no secrets: it
asks the game for its player count the way the in-game server list does.
Carpet bots are players to the server, so they keep it running too.

    idle_check.py --state FILE [--host mc.cactuz.dev] [--idle-minutes 120] [--max-days 7]

The state file remembers when the VPS was first seen and when someone was last
online. Prints the decision; writes stop=true|false to $GITHUB_OUTPUT if set.
"""

import argparse
import json
import os
import socket
import struct
import sys
import time


def varint(n):
    out = b""
    n &= 0xFFFFFFFF
    while True:
        byte = n & 0x7F
        n >>= 7
        if n:
            out += bytes([byte | 0x80])
        else:
            return out + bytes([byte])


def read_varint(sock):
    n = shift = 0
    while True:
        byte = sock.recv(1)
        if not byte:
            raise ConnectionError("connection closed")
        n |= (byte[0] & 0x7F) << shift
        if not byte[0] & 0x80:
            return n
        shift += 7
        if shift > 35:
            raise ValueError("varint too long")


def read_exact(sock, size):
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("connection closed")
        data += chunk
    return data


def players_online(address, host, port, timeout=5):
    """Server List Ping: returns the number of players (bots included) online."""
    with socket.create_connection((address, port), timeout=timeout) as sock:
        name = host.encode()
        handshake = (varint(0) + varint(-1) + varint(len(name)) + name
                     + struct.pack(">H", port) + varint(1))
        sock.sendall(varint(len(handshake)) + handshake + varint(1) + varint(0))
        read_varint(sock)  # packet length
        if read_varint(sock) != 0:
            raise ValueError("unexpected packet")
        status = json.loads(read_exact(sock, read_varint(sock)))
        return int(status["players"]["online"])


def vps_address(host):
    """The VPS's IPv4 address, or None when the DNS record is gone (no VPS)."""
    try:
        return socket.getaddrinfo(host, None, socket.AF_INET)[0][4][0]
    except socket.gaierror:
        return None


def decide(state, online, now, idle_minutes, max_days):
    """Updates state in place and returns (stop, reason)."""
    state.setdefault("up_since", now)
    state.setdefault("last_busy", now)
    if online:
        state["last_busy"] = now
    idle = now - state["last_busy"]
    up = now - state["up_since"]
    if up >= max_days * 86400:
        return True, f"up for {up // 3600} hours, over the {max_days}-day cap"
    if idle >= idle_minutes * 60:
        return True, f"nobody online for {idle // 60} minutes"
    if online is None:
        return False, f"the game did not answer; idle for {idle // 60} minutes so far"
    return False, f"{online} online; idle for {idle // 60} minutes"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    parser.add_argument("--host", default="mc.cactuz.dev")
    parser.add_argument("--port", type=int, default=25565)
    parser.add_argument("--idle-minutes", type=int, default=120)
    parser.add_argument("--max-days", type=int, default=7)
    args = parser.parse_args()

    now = int(time.time())
    try:
        with open(args.state) as f:
            state = json.load(f)
    except (OSError, ValueError):
        state = {}

    address = vps_address(args.host)
    if address is None:
        stop, reason, state = False, "no VPS (no DNS record)", {}
    else:
        if state.get("address") != address:
            state = {"address": address}  # a new VPS: start its clocks fresh
        try:
            online = players_online(address, args.host, args.port)
        except (OSError, ValueError, KeyError):
            online = None  # starting up, or the game is down: counts as idle
        stop, reason = decide(state, online, now, args.idle_minutes, args.max_days)

    os.makedirs(os.path.dirname(os.path.abspath(args.state)), exist_ok=True)
    with open(args.state, "w") as f:
        json.dump(state, f)
    print(("stop: " if stop else "no stop: ") + reason)
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"stop={'true' if stop else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
