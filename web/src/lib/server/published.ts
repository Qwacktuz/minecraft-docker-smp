// vps.json, players.json and leaderboard.json in the WEB bucket, written on the
// VPS by scripts/publish-status.sh at every start and stop (vps.json: start only).
import type { Leaderboard } from '../leaderboard';
import type { Players, Vps } from '../vps';
import type { Env } from './env';

async function readJson<T>(env: Env, key: string): Promise<T | null> {
	const object = await env.WEB.get(key);
	return object ? ((await object.json()) as T) : null;
}

export const getVps = (env: Env) => readJson<Vps>(env, 'vps.json');
export const getPlayers = (env: Env) => readJson<Players>(env, 'players.json');
export const getLeaderboard = (env: Env) => readJson<Leaderboard>(env, 'leaderboard.json');
