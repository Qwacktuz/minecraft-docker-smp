import { json } from '@sveltejs/kit';
import { env } from '#lib/server/env.ts';
import { getRuns } from '#lib/server/runs.ts';
import type { RequestHandler } from './$types';

// Polled by the admin page while a run is in flight. /admin/* is behind Access (hooks.server.ts).
export const GET: RequestHandler = async () => {
	try {
		return json(await getRuns(env), { headers: { 'cache-control': 'no-store' } });
	} catch (e) {
		return json({ error: (e as Error).message }, { status: 502 });
	}
};
