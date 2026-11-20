import { github, recentRuns } from '../../../../watchdog/src/minecraft.js';
import { toRun, type Run } from '../runs';
import type { Env } from './env';

/** The newest Server runs; unfinished ones come with their steps. */
export async function getRuns(env: Env, count = 8): Promise<Run[]> {
	const runs = await recentRuns(env, count);
	return Promise.all(
		runs.map(async (run) => {
			if (run.status === 'completed') return toRun(run);
			const response = await github(env, `/actions/runs/${run.id}/jobs`);
			return toRun(run, response.ok ? (await response.json()).jobs : undefined);
		})
	);
}
