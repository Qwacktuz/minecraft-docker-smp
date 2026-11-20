import { env } from '#lib/server/env.ts';
import { getStatus } from '#lib/server/status.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => ({
	status: await getStatus(env),
	host: env.HOST,
	worldUrl: env.WORLD_URL,
	idleMinutes: Number(env.IDLE_MINUTES),
	maxDays: Number(env.MAX_DAYS)
});
