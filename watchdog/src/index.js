// Idle auto-stop for the Minecraft VPS, run by a Cloudflare cron trigger.
//
// Every 5 minutes: is there a VPS (DNS record for HOST)? How many players are
// online (server list ping; Carpet bots count)? After IDLE_MINUTES with nobody
// online, or MAX_DAYS of uptime, it starts the GitHub "Server" workflow with
// action=stop, which backs up, verifies and deletes the VPS (bin/server stop).
//
// It holds one secret, GITHUB_TOKEN: a fine-grained token that can only run
// workflows in this repository. GET / shows the current state (no secrets).
import { decide, shouldDispatch } from "./logic.js";
import { dispatch, playersOnline, runsInFlight, vpsAddress } from "./minecraft.js";

async function check(env) {
  const now = Math.floor(Date.now() / 1000);
  const previous = (await env.STATE.get("state", "json")) ?? {};
  const address = await vpsAddress(env.HOST);
  const online = address === null ? null : await playersOnline(address, env.HOST, Number(env.PORT));
  const config = { idleMinutes: Number(env.IDLE_MINUTES), maxDays: Number(env.MAX_DAYS) };
  const { stop, reason, state } = decide(previous, address, online, now, config);
  let action = "none";
  if (stop) {
    if (shouldDispatch(state, await runsInFlight(env), now)) {
      await dispatch(env, "stop");
      state.last_dispatch = now;
      action = "requested a stop";
    } else {
      action = "a stop is already under way or was just requested";
    }
  }
  // KV writes are limited on the free plan: write only when something changed.
  if (JSON.stringify(state) !== JSON.stringify(previous)) await env.STATE.put("state", JSON.stringify(state));
  const result = { checked: new Date(now * 1000).toISOString(), stop, reason, action, online, state };
  console.log(JSON.stringify(result));
  return result;
}

export default {
  async scheduled(_controller, env, ctx) {
    ctx.waitUntil(check(env));
  },
  // A read-only look at the last decision (player counts are public anyway).
  async fetch(_request, env) {
    const state = (await env.STATE.get("state", "json")) ?? {};
    return Response.json({ host: env.HOST, idle_minutes: Number(env.IDLE_MINUTES), max_days: Number(env.MAX_DAYS), state });
  },
};
