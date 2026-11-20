import { error } from '@sveltejs/kit';
import type { Handle } from '@sveltejs/kit/hooks';
import { dev } from '$app/env';
import { accessEmail } from '#lib/server/access.ts';
import { env } from '#lib/server/env.ts';

export const handle: Handle = async ({ event, resolve }) => {
	if (event.url.pathname === '/admin' || event.url.pathname.startsWith('/admin/')) {
		// `npm run dev` has no Access in front of it.
		const email = dev ? 'dev@localhost' : await accessEmail(event.request, env);
		if (!email) error(403, 'Sign in through Cloudflare Access to use the admin page.');
		event.locals.admin = email;
	}
	return resolve(event);
};
