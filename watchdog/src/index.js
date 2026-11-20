// Idle auto-stop for the Minecraft VPS, run by a Cloudflare cron trigger.
//
// Every 5 minutes: is there a VPS (DNS record for HOST)? How many players are
// online (server list ping; Carpet bots count)? After IDLE_MINUTES with nobody
// online, or MAX_DAYS of uptime, it starts the GitHub "Server" workflow with
// action=stop, which backs up, verifies and deletes the VPS (bin/server stop).
//
// It holds one secret, GITHUB_TOKEN: a fine-grained token that can only run
// workflows in this repository. GET / shows the current state (no secrets).
import { connect } from "cloudflare:sockets";
import { decide, parseStatus, shouldDispatch, statusRequest } from "./logic.js";

const PING_TIMEOUT_MS = 5000;

async function vpsAddress(host) {
  const url = `https://cloudflare-dns.com/dns-query?name=${encodeURIComponent(host)}&type=A`;
  const response = await fetch(url, { headers: { accept: "application/dns-json" } });
  if (!response.ok) throw new Error(`DNS lookup failed: ${response.status}`);
  const answer = (await response.json()).Answer?.find((record) => record.type === 1);
  return answer ? answer.data : null;
}

/** Players online, or null when the game doesn't answer. */
async function playersOnline(address, host, port) {
  let socket;
  const timeout = new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), PING_TIMEOUT_MS));
  try {
    socket = connect({ hostname: address, port });
    const ping = (async () => {
      const writer = socket.writable.getWriter();
      await writer.write(statusRequest(host, port));
      const reader = socket.readable.getReader();
      let bytes = new Uint8Array(0);
      for (;;) {
        const { value, done } = await reader.read();
        if (done) throw new Error("connection closed");
        const joined = new Uint8Array(bytes.length + value.length);
        joined.set(bytes);
        joined.set(value, bytes.length);
        bytes = joined;
        const online = parseStatus(bytes);
        if (online !== null) return online;
      }
    })();
    return await Promise.race([ping, timeout]);
  } catch {
    return null;
  } finally {
    socket?.close().catch(() => {});
  }
}

function github(env, path, init = {}) {
  return fetch(`https://api.github.com/repos/${env.REPO}${path}`, {
    ...init,
    headers: {
      accept: "application/vnd.github+json",
      authorization: `Bearer ${env.GITHUB_TOKEN}`,
      "user-agent": "mc-idle-watchdog",
      "x-github-api-version": "2022-11-28",
      ...init.headers,
    },
  });
}

async function runsInFlight(env) {
  const response = await github(env, `/actions/workflows/${env.WORKFLOW}/runs?per_page=10`);
  if (!response.ok) throw new Error(`listing runs failed: ${response.status}`);
  const { workflow_runs: runs } = await response.json();
  return runs.filter((run) => run.status !== "completed").length;
}

async function requestStop(env) {
  const response = await github(env, `/actions/workflows/${env.WORKFLOW}/dispatches`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ref: "main", inputs: { action: "stop" } }),
  });
  if (response.status !== 204) throw new Error(`starting the stop failed: ${response.status} ${await response.text()}`);
}

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
      await requestStop(env);
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
