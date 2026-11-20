// Server workflow runs, trimmed to what the admin page shows. Pure, for tests.
import type { WorkflowRun } from '../../../watchdog/src/minecraft.js';

export interface Step {
	name: string;
	status: string;
	conclusion: string | null;
}

export interface Run {
	id: number;
	/** "start" or "stop", from the run's title ("bin/server stop"), or null. */
	action: string | null;
	status: string;
	conclusion: string | null;
	by: string | null;
	url: string;
	created: string;
	updated: string;
	steps?: Step[];
}

interface Job {
	steps?: { name: string; status: string; conclusion: string | null }[];
}

export function toRun(run: WorkflowRun, jobs?: Job[]): Run {
	const action = /\b(start|stop)\b/.exec(run.display_title)?.[1] ?? null;
	return {
		id: run.id,
		action,
		status: run.status,
		conclusion: run.conclusion,
		by: run.triggering_actor?.login ?? run.actor?.login ?? null,
		url: run.html_url,
		created: run.created_at,
		updated: run.updated_at,
		steps: jobs?.flatMap((job) =>
			(job.steps ?? [])
				// GitHub's own bookkeeping steps say nothing about the server.
				.filter((step) => !/^(Set up job|Complete job|Post )/.test(step.name))
				.map(({ name, status, conclusion }) => ({ name, status, conclusion }))
		)
	};
}
