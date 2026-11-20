import assert from "node:assert/strict";
import { test } from "node:test";
import { decide, parseStatus, readVarint, shouldDispatch, statusRequest, varint } from "../src/logic.js";

const HOUR = 3600;
const config = { idleMinutes: 120, maxDays: 7 };
const ip = "192.0.2.1";

test("varint round-trips, including -1", () => {
  for (const n of [0, 1, 127, 128, 25565, 2 ** 31 - 1]) assert.equal(readVarint(varint(n), 0)[0], n);
  assert.deepEqual(varint(-1), [0xff, 0xff, 0xff, 0xff, 0x0f]);
});

test("status request starts with its length and ends with the status request", () => {
  const bytes = statusRequest("mc.cactuz.dev", 25565);
  const [length, start] = readVarint(bytes, 0);
  assert.equal(bytes.length, start + length + 2);
  assert.deepEqual([...bytes.slice(-2)], [1, 0]);
});

function statusPacket(online) {
  const body = new TextEncoder().encode(JSON.stringify({ players: { online, max: 20 }, description: "x".repeat(300) }));
  const packet = [...varint(0), ...varint(body.length), ...body];
  return new Uint8Array([...varint(packet.length), ...packet]);
}

test("parses the player count, waiting for the whole packet", () => {
  const bytes = statusPacket(3);
  assert.equal(parseStatus(bytes.subarray(0, 10)), null);
  assert.equal(parseStatus(bytes), 3);
});

test("no DNS record means no VPS and clears the state", () => {
  const result = decide({ address: ip, up_since: 0, last_busy: 0 }, null, null, 10 * HOUR, config);
  assert.equal(result.stop, false);
  assert.deepEqual(result.state, {});
});

test("players (bots too) keep it running", () => {
  const result = decide({ address: ip, up_since: 0, last_busy: 0 }, ip, 1, 3 * HOUR, config);
  assert.equal(result.stop, false);
  assert.equal(result.state.last_busy, 3 * HOUR);
});

test("stops after two idle hours, not before", () => {
  const state = { address: ip, up_since: 0, last_busy: 0 };
  assert.equal(decide(state, ip, 0, 2 * HOUR - 60, config).stop, false);
  assert.equal(decide(state, ip, 0, 2 * HOUR, config).stop, true);
});

test("a game that doesn't answer counts as idle", () => {
  assert.equal(decide({ address: ip, up_since: 0, last_busy: 0 }, ip, null, 2 * HOUR, config).stop, true);
});

test("a new VPS starts its clocks fresh", () => {
  const result = decide({ address: "198.51.100.7", up_since: 0, last_busy: 0 }, ip, 0, 10 * HOUR, config);
  assert.equal(result.stop, false);
  assert.deepEqual(result.state, { address: ip, up_since: 10 * HOUR, last_busy: 10 * HOUR });
});

test("the 7-day cap stops even with players online", () => {
  const result = decide({ address: ip, up_since: 0, last_busy: 0 }, ip, 4, 7 * 24 * HOUR, config);
  assert.equal(result.stop, true);
  assert.match(result.reason, /cap/);
});

test("dispatches once, not while a run is in flight or right after a request", () => {
  assert.equal(shouldDispatch({}, 0, 1000), true);
  assert.equal(shouldDispatch({}, 1, 1000), false);
  assert.equal(shouldDispatch({ last_dispatch: 1000 }, 0, 1000 + 29 * 60), false);
  assert.equal(shouldDispatch({ last_dispatch: 1000 }, 0, 1000 + 30 * 60), true);
});
