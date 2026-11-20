import { env } from '#lib/server/env.ts';
import { getLeaderboard } from '#lib/server/published.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ setHeaders }) => {
	// It changes at a start or stop at most: let browsers and Cloudflare reuse it briefly.
	setHeaders({ 'cache-control': 'public, max-age=300' });
	return { leaderboard: await getLeaderboard(env).catch(() => null) };
};
