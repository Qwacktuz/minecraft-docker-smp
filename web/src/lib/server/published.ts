// vps.json and players.json in the WEB bucket, written on the VPS by
// scripts/publish-status.sh at every start (both) and stop (players.json).
import type { Players, Vps } from '../vps';
import type { Env } from './env';

async function readJson<T>(env: Env, key: string): Promise<T | null> {
	const object = await env.WEB.get(key);
	return object ? ((await object.json()) as T) : null;
}

export const getVps = (env: Env) => readJson<Vps>(env, 'vps.json');
export const getPlayers = (env: Env) => readJson<Players>(env, 'players.json');
