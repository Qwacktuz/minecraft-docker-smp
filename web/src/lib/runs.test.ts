import { expect, test } from 'vitest';
import { toRun } from './runs';

const base = {
	id: 1,
	status: 'in_progress',
	conclusion: null,
	event: 'workflow_dispatch',
	display_title: 'Server',
	html_url: 'https://github.com/x/y/actions/runs/1',
	created_at: '2026-11-20T10:00:00Z',
	updated_at: '2026-11-20T10:01:00Z',
	triggering_actor: { login: 'someone' }
};

test('reads the action from the job title and drops GitHub bookkeeping steps', () => {
	const run = toRun({ ...base, display_title: 'bin/server stop' }, [
		{
			steps: [
				{ name: 'Set up job', status: 'completed', conclusion: 'success' },
				{ name: 'Reach the VPS by its Tailscale name', status: 'completed', conclusion: 'success' },
				{ name: 'bin/server stop', status: 'in_progress', conclusion: null },
				{ name: 'Post Run actions/checkout', status: 'queued', conclusion: null }
			]
		}
	]);
	expect(run.action).toBe('stop');
	expect(run.by).toBe('someone');
	expect(run.steps?.map((s) => s.name)).toEqual(['Reach the VPS by its Tailscale name', 'bin/server stop']);
});

test('unknown title: no action, no steps for finished runs', () => {
	const run = toRun({ ...base, status: 'completed', conclusion: 'success' });
	expect(run.action).toBeNull();
	expect(run.steps).toBeUndefined();
});
