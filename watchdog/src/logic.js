// Pure logic for the idle watchdog, shared by the Worker and its tests.
// It mirrors scripts/idle_check.py.

/** Minecraft protocol VarInt. */
export function varint(n) {
  const out = [];
  let v = n >>> 0;
  do {
    let byte = v & 0x7f;
    v >>>= 7;
    if (v) byte |= 0x80;
    out.push(byte);
  } while (v);
  return out;
}

/** Reads a VarInt at offset; returns [value, nextOffset] or null if incomplete. */
export function readVarint(bytes, offset) {
  let value = 0;
  for (let i = 0; i < 5; i++) {
    if (offset + i >= bytes.length) return null;
    const byte = bytes[offset + i];
    value |= (byte & 0x7f) << (7 * i);
    if (!(byte & 0x80)) return [value >>> 0, offset + i + 1];
  }
  throw new Error("varint too long");
}

/** Handshake (next state: status) followed by a status request. */
export function statusRequest(host, port) {
  const name = new TextEncoder().encode(host);
  const handshake = [
    ...varint(0), // packet id
    ...varint(-1), // protocol version: any
    ...varint(name.length), ...name,
    (port >> 8) & 0xff, port & 0xff,
    ...varint(1), // next state: status
  ];
  return new Uint8Array([...varint(handshake.length), ...handshake, ...varint(1), ...varint(0)]);
}

/** The UUID the server lists for players who turned off "Allow Server Listings". */
const ANONYMOUS = "00000000-0000-0000-0000-000000000000";

/**
 * Parses a status response from the bytes received so far.
 * Returns { online, max, names }, or null while more bytes are needed. names is
 * the server's sample of who's online (vanilla lists up to 12), sorted, without
 * anonymous entries or formatting codes. It can be shorter than online.
 */
export function parseStatusDetails(bytes) {
  const length = readVarint(bytes, 0);
  if (!length) return null;
  const [packetLength, start] = length;
  if (bytes.length < start + packetLength) return null;
  const id = readVarint(bytes, start);
  if (!id || id[0] !== 0) throw new Error("unexpected packet");
  const text = readVarint(bytes, id[1]);
  if (!text) throw new Error("truncated status");
  const json = new TextDecoder().decode(bytes.subarray(text[1], text[1] + text[0]));
  const players = JSON.parse(json).players;
  const names = (Array.isArray(players.sample) ? players.sample : [])
    .filter((player) => typeof player?.name === "string" && player.id !== ANONYMOUS)
    .map((player) => player.name.replace(/\u00a7./g, "").trim())
    .filter(Boolean)
    .sort((a, b) => a.localeCompare(b, "en", { sensitivity: "base" }));
  return { online: Number(players.online), max: Number(players.max), names };
}

/** Players online from a status response, or null while more bytes are needed. */
export function parseStatus(bytes) {
  return parseStatusDetails(bytes)?.online ?? null;
}

/**
 * Updates the state and decides whether to stop the VPS.
 * address: the VPS's IPv4 address, or null when the DNS record is gone (no VPS).
 * online: players online (Carpet bots count), or null when the game didn't answer.
 * Returns { stop, reason, state }.
 */
export function decide(previous, address, online, now, { idleMinutes, maxDays }) {
  if (address === null) return { stop: false, reason: "no VPS (no DNS record)", state: {} };
  // A new VPS (new address) starts its clocks fresh.
  const state = previous.address === address ? { ...previous } : { address };
  state.up_since ??= now;
  state.last_busy ??= now;
  if (online) state.last_busy = now;
  const idle = now - state.last_busy;
  const up = now - state.up_since;
  if (up >= maxDays * 86400)
    return { stop: true, reason: `up for ${Math.floor(up / 3600)} hours, over the ${maxDays}-day cap`, state };
  if (idle >= idleMinutes * 60)
    return { stop: true, reason: `nobody online for ${Math.floor(idle / 60)} minutes`, state };
  const who = online === null ? "the game did not answer" : `${online} online`;
  return { stop: false, reason: `${who}; idle for ${Math.floor(idle / 60)} minutes`, state };
}

/** True when a stop should be requested now: no run in flight, none requested recently. */
export function shouldDispatch(state, runsInFlight, now, cooldownMinutes = 30) {
  if (runsInFlight > 0) return false;
  return !state.last_dispatch || now - state.last_dispatch >= cooldownMinutes * 60;
}

/** The KV key for one month's VPS uptime (UTC): "usage:2026-11". */
export function usageKey(now) {
  const date = new Date(now * 1000);
  return `usage:${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
}

/**
 * Adds one check's worth of uptime to a month's usage, under the server type
 * that ran (Hetzner prices differ per type; "unknown" when it isn't known).
 * since: when this month was first counted (a month that started before the
 * watchdog counted shows less than it ran).
 */
export function addUsage(usage, minutes, now, type = "unknown") {
  const byType = { ...usage?.by_type };
  byType[type] = (byType[type] ?? 0) + minutes;
  return { since: usage?.since ?? now, minutes: (usage?.minutes ?? 0) + minutes, by_type: byType };
}

/**
 * The server type from vps.json (written by the VPS at a start), when it
 * describes the VPS at this address; "unknown" otherwise (a VPS still starting,
 * or an older VPS's file).
 */
export function vpsType(vps, address) {
  return vps && vps.ipv4 === address && /^[a-z0-9]+$/.test(vps.type ?? "") ? vps.type : "unknown";
}
