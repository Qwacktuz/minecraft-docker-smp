// Talking to the game and to GitHub, shared by the watchdog Worker (index.js)
// and the web app (web/). Needs the Workers runtime (cloudflare:sockets).
//
// env: HOST, PORT, REPO, WORKFLOW, GITHUB_TOKEN.
import { parseStatus, statusRequest } from "./logic.js";

const PING_TIMEOUT_MS = 5000;

/** The VPS's IPv4 address from its DNS record, or null when there is no VPS. */
export async function vpsAddress(host) {
  const url = `https://cloudflare-dns.com/dns-query?name=${encodeURIComponent(host)}&type=A`;
  const response = await fetch(url, { headers: { accept: "application/dns-json" } });
  if (!response.ok) throw new Error(`DNS lookup failed: ${response.status}`);
  const answer = (await response.json()).Answer?.find((record) => record.type === 1);
  return answer ? answer.data : null;
}

/** Players online, or null when the game doesn't answer. */
export async function playersOnline(address, host, port) {
  let socket;
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error("timeout")), PING_TIMEOUT_MS);
  });
  try {
    // Imported here, not at the top: SvelteKit loads this module in Node while
    // building the web app, and Node can't load cloudflare: URLs.
    const { connect } = await import("cloudflare:sockets");
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
    clearTimeout(timer);
    socket?.close().catch(() => {});
  }
}

/** A GitHub API request for this repository, with the Worker's token. */
export function github(env, path, init = {}) {
  return fetch(`https://api.github.com/repos/${env.REPO}${path}`, {
    ...init,
    headers: {
      accept: "application/vnd.github+json",
      authorization: `Bearer ${env.GITHUB_TOKEN}`,
      "user-agent": "mc-smp-worker",
      "x-github-api-version": "2022-11-28",
      ...init.headers,
    },
  });
}

/** The Server workflow's newest runs (GitHub's run objects). */
export async function recentRuns(env, count = 10) {
  const response = await github(env, `/actions/workflows/${env.WORKFLOW}/runs?per_page=${count}`);
  if (!response.ok) throw new Error(`listing runs failed: ${response.status}`);
  return (await response.json()).workflow_runs;
}

/** How many Server runs are queued or running. */
export async function runsInFlight(env) {
  return (await recentRuns(env)).filter((run) => run.status !== "completed").length;
}

/** Starts the Server workflow on main with action=start|stop. */
export async function dispatch(env, action) {
  if (action !== "start" && action !== "stop") throw new Error(`unknown action: ${action}`);
  const response = await github(env, `/actions/workflows/${env.WORKFLOW}/dispatches`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ref: "main", inputs: { action } }),
  });
  if (response.status !== 204) throw new Error(`starting the ${action} failed: ${response.status} ${await response.text()}`);
}
