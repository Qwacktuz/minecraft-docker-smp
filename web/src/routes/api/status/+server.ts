import { json } from '@sveltejs/kit';
import { env } from '#lib/server/env.ts';
import { getStatus } from '#lib/server/status.ts';
import type { RequestHandler } from './$types';

// Public: the same numbers anyone gets from the server list in the game.
export const GET: RequestHandler = async () =>
	json(await getStatus(env), { headers: { 'cache-control': 'public, max-age=15' } });
