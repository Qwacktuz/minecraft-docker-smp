// `cloudflare:workers` exists only in the Workers runtime; src/lib/server/env.ts types its env.
declare module 'cloudflare:workers' {
	export const env: Record<string, unknown>;
}
