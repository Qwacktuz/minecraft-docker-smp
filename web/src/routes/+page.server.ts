import { env } from '#lib/server/env.ts';
import { getVps } from '#lib/server/published.ts';
import { getStatusAndAddress } from '#lib/server/status.ts';
import { current } from '#lib/vps.ts';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	const [{ status, address }, vps] = await Promise.all([
		getStatusAndAddress(env),
		getVps(env).catch(() => null)
	]);
	return {
		status,
		// The hardware only, for the VPS that runs now: no address or CPU model on the public page.
		hardware: (() => {
			const now = current(vps, address);
			return now && { type: now.type, location: now.location, cpus: now.cpus, memory_bytes: now.memory_bytes };
		})(),
		host: env.HOST,
		worldUrl: env.WORLD_URL,
		idleMinutes: Number(env.IDLE_MINUTES),
		maxDays: Number(env.MAX_DAYS)
	};
};
