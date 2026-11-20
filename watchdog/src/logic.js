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

/**
 * Parses a status response from the bytes received so far.
 * Returns the number of players online, or null while more bytes are needed.
 */
export function parseStatus(bytes) {
  const length = readVarint(bytes, 0);
  if (!length) return null;
  const [packetLength, start] = length;
  if (bytes.length < start + packetLength) return null;
  const id = readVarint(bytes, start);
  if (!id || id[0] !== 0) throw new Error("unexpected packet");
  const text = readVarint(bytes, id[1]);
  if (!text) throw new Error("truncated status");
  const json = new TextDecoder().decode(bytes.subarray(text[1], text[1] + text[0]));
  return Number(JSON.parse(json).players.online);
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
