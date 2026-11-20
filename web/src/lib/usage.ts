// The VPS's monthly uptime, counted by the watchdog (usage:YYYY-MM in KV), and
// what it roughly costs. Pure, so it runs in tests.
import type { Usage } from '../../../watchdog/src/logic.js';

export interface MonthUsage {
	/** "November 2026". */
	label: string;
	hours: number;
	/** Euros, or null without a price. */
	cost: number | null;
	/** Unix seconds when counting started, when that was after the month began. */
	countedSince: number | null;
}

export function monthUsage(usage: Usage | null, monthStart: Date, price: number | null): MonthUsage {
	const hours = (usage?.minutes ?? 0) / 60;
	const begins = monthStart.getTime() / 1000;
	return {
		label: monthStart.toLocaleString('en-GB', { month: 'long', year: 'numeric', timeZone: 'UTC' }),
		hours,
		cost: price === null ? null : hours * price,
		// More than a check after the month began: the watchdog started counting late.
		countedSince: usage && usage.since > begins + 600 ? usage.since : null
	};
}

/** "12.5" from "12.5", null for "" or nonsense. */
export function parsePrice(value: string | undefined): number | null {
	const price = Number(value);
	return value && Number.isFinite(price) && price > 0 ? price : null;
}

/** The first moments of this UTC month and the one before. */
export function months(now: Date): [Date, Date] {
	const year = now.getUTCFullYear();
	const month = now.getUTCMonth();
	return [new Date(Date.UTC(year, month, 1)), new Date(Date.UTC(year, month - 1, 1))];
}
