// See https://svelte.dev/docs/kit/types#app.d.ts
// The Worker's bindings are in src/lib/server/env.ts.
declare global {
	namespace App {
		interface Locals {
			/** The admin's email from Cloudflare Access, on /admin routes only. */
			admin?: string;
		}
	}
}

export {};
