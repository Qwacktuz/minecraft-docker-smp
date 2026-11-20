import { fail } from '@sveltejs/kit';
import { dispatch, runsInFlight } from '../../../../watchdog/src/minecraft.js';
import { env } from '#lib/server/env.ts';
import { getBackups } from '#lib/server/backups.ts';
import { getRuns } from '#lib/server/runs.ts';
import { getPlayers, getVps } from '#lib/server/published.ts';
import { getStatusAndAddress } from '#lib/server/status.ts';
import { getUsage } from '#lib/server/usage.ts';
import { current } from '#lib/vps.ts';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals }) => {
	const [{ status, address }, runs, backups, vps, players, usage] = await Promise.all([
		getStatusAndAddress(env),
		getRuns(env).catch((e: Error) => e.message),
		getBackups(env).catch(() => null),
		getVps(env).catch(() => null),
		getPlayers(env).catch(() => null),
		getUsage(env).catch(() => null)
	]);
	return { admin: locals.admin, status, runs, backups, vps: current(vps, address), players, usage, host: env.HOST };
};

// Start/stop run the same GitHub workflow as the "Run workflow" button and the
// watchdog: bin/server on a runner, always from main.
async function run(action: 'start' | 'stop', admin?: string) {
	try {
		if ((await runsInFlight(env)) > 0)
			return fail(409, { message: 'A start or stop is already running; wait for it to finish.' });
		await dispatch(env, action);
	} catch (e) {
		return fail(502, { message: (e as Error).message });
	}
	console.log(JSON.stringify({ event: 'dispatch', action, admin }));
	return { message: `Requested a ${action}. It shows up below in a few seconds.` };
}

export const actions: Actions = {
	start: ({ locals }) => run('start', locals.admin),
	stop: ({ locals }) => run('stop', locals.admin)
};
