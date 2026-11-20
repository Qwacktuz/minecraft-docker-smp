// The live status: DNS + server list ping (shared with the watchdog) and the
// watchdog's KV state. The ping is cached for 30 s so page loads don't each
// open a connection to the game.
import { serverStatus, vpsAddress } from '../../../../watchdog/src/minecraft.js';
import type { WatchdogState } from '../../../../watchdog/src/logic.js';
import { describe, type Status } from '../status';
import type { Env } from './env';

const CACHE_SECONDS = 30;

interface Ping {
	address: string | null;
	online: number | null;
	names: string[];
}

/**
 * The VPS's address from DNS, tried twice. When both lookups fail (a network
 * error or a bad answer), it falls back to the address the watchdog last saw,
 * so a DNS hiccup doesn't fail the page; `guessed` keeps that out of the cache.
 */
async function lookup(env: Env, state: WatchdogState): Promise<{ address: string | null; guessed: boolean }> {
	// HOST=localhost in .dev.vars pings a local copy (`server start local`) in `npm run dev`.
	if (env.HOST === 'localhost') return { address: '127.0.0.1', guessed: false };
	for (let attempt = 1; ; attempt++) {
		try {
			return { address: await vpsAddress(env.HOST), guessed: false };
		} catch (e) {
			if (attempt < 2) continue;
			console.error(JSON.stringify({ event: 'dns-lookup-failed', host: env.HOST, error: (e as Error).message }));
			return { address: state.address ?? null, guessed: true };
		}
	}
}

async function ping(env: Env, state: WatchdogState): Promise<Ping & { guessed: boolean }> {
	const { address, guessed } = await lookup(env, state);
	// `npm run dev` runs this in Node, which has no cloudflare:sockets.
	// import.meta.env.DEV is replaced at build time, so the Worker build leaves ping-node out.
	const statusOf = import.meta.env.DEV ? (await import('./ping-node')).nodeServerStatus : serverStatus;
	const status = address === null ? null : await statusOf(address, env.HOST, Number(env.PORT));
	return { address, online: status?.online ?? null, names: status?.names ?? [], guessed };
}

export async function getStatus(env: Env): Promise<Status> {
	return (await getStatusAndAddress(env)).status;
}

/** The status, plus the address DNS points at (null when there is no VPS). */
export async function getStatusAndAddress(env: Env): Promise<{ status: Status; address: string | null }> {
	const state = ((await env.STATE.get('state', 'json')) ?? {}) as WatchdogState;
	// The Cache API needs a URL key; it never leaves this data centre.
	const key = new Request(`https://cache.internal/status/${env.HOST}`);
	const cache = (globalThis as { caches?: { default?: Cache } }).caches?.default;
	const hit = await cache?.match(key);
	let result = hit ? ((await hit.json()) as Ping & { at: number }) : undefined;
	if (!result) {
		const { guessed, ...fresh } = await ping(env, state);
		result = { ...fresh, at: Math.floor(Date.now() / 1000) };
		if (!guessed)
			await cache?.put(
				key,
				new Response(JSON.stringify(result), { headers: { 'cache-control': `max-age=${CACHE_SECONDS}` } })
			);
	}
	const status = describe(result.address, result.online, state, result.at, {
		idleMinutes: Number(env.IDLE_MINUTES),
		maxDays: Number(env.MAX_DAYS)
	}, result.names ?? []);
	return { status, address: result.address };
}
