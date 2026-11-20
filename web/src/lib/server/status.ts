// The live status: DNS + server list ping (shared with the watchdog) and the
// watchdog's KV state. The ping is cached for 30 s so page loads don't each
// open a connection to the game.
import { playersOnline, vpsAddress } from '../../../../watchdog/src/minecraft.js';
import type { WatchdogState } from '../../../../watchdog/src/logic.js';
import { describe, type Status } from '../status';
import type { Env } from './env';

const CACHE_SECONDS = 30;

async function ping(env: Env): Promise<{ address: string | null; online: number | null }> {
	// HOST=localhost in .dev.vars pings a local copy (`server start local`) in `npm run dev`.
	const address = env.HOST === 'localhost' ? '127.0.0.1' : await vpsAddress(env.HOST);
	const online = address === null ? null : await playersOnline(address, env.HOST, Number(env.PORT));
	return { address, online };
}

export async function getStatus(env: Env): Promise<Status> {
	// The Cache API needs a URL key; it never leaves this data centre.
	const key = new Request(`https://cache.internal/status/${env.HOST}`);
	const cache = (globalThis as { caches?: { default?: Cache } }).caches?.default;
	const hit = await cache?.match(key);
	let result = hit ? ((await hit.json()) as { address: string | null; online: number | null; at: number }) : undefined;
	if (!result) {
		result = { ...(await ping(env)), at: Math.floor(Date.now() / 1000) };
		await cache?.put(
			key,
			new Response(JSON.stringify(result), { headers: { 'cache-control': `max-age=${CACHE_SECONDS}` } })
		);
	}
	const state = ((await env.STATE.get('state', 'json')) ?? {}) as WatchdogState;
	return describe(result.address, result.online, state, result.at, {
		idleMinutes: Number(env.IDLE_MINUTES),
		maxDays: Number(env.MAX_DAYS)
	});
}
