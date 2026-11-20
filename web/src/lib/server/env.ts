// The Worker's bindings and vars (web/wrangler.toml). adapter-cloudflare gives
// them through `cloudflare:workers`, in `npm run dev` too (local KV and R2).
import { env as bindings } from 'cloudflare:workers';
import type { KVNamespace, R2Bucket } from '@cloudflare/workers-types';

export interface Env {
	HOST: string;
	PORT: string;
	IDLE_MINUTES: string;
	MAX_DAYS: string;
	REPO: string;
	WORKFLOW: string;
	WORLD_URL: string;
	MAP_URL: string;
	/** Euros per hour, or "" for hours only. */
	HOURLY_PRICE_EUR: string;
	ACCESS_TEAM_DOMAIN: string;
	ACCESS_AUD: string;
	/** A secret: `wrangler secret put GITHUB_TOKEN` (server web), or .dev.vars. */
	GITHUB_TOKEN: string;
	STATE: KVNamespace;
	WEB: R2Bucket;
}

export const env = bindings as unknown as Env;
