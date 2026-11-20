// The watchdog's monthly uptime count (watchdog/src/index.js) for the admin page.
import { usageKey, type Usage } from '../../../../watchdog/src/logic.js';
import { monthUsage, months, parsePrices, type MonthUsage } from '../usage';
import type { Env } from './env';

/** This month and last month, newest first. */
export async function getUsage(env: Env, now = new Date()): Promise<MonthUsage[]> {
	const prices = parsePrices(env.HOURLY_PRICES_EUR);
	return Promise.all(
		months(now).map(async (start) => {
			const usage = (await env.STATE.get(usageKey(start.getTime() / 1000), 'json')) as Usage | null;
			return monthUsage(usage, start, prices);
		})
	);
}
