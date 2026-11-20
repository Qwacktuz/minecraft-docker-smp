// The watchdog's monthly uptime count (watchdog/src/index.js) for the admin page.
import { usageKey, type Usage } from '../../../../watchdog/src/logic.js';
import { monthUsage, months, parsePrice, type MonthUsage } from '../usage';
import type { Env } from './env';

/** This month and last month, newest first. */
export async function getUsage(env: Env, now = new Date()): Promise<MonthUsage[]> {
	const price = parsePrice(env.HOURLY_PRICE_EUR);
	return Promise.all(
		months(now).map(async (start) => {
			const usage = (await env.STATE.get(usageKey(start.getTime() / 1000), 'json')) as Usage | null;
			return monthUsage(usage, start, price);
		})
	);
}
