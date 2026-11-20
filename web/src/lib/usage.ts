// The VPS's monthly uptime per server type, counted by the watchdog
// (usage:YYYY-MM in KV), and what it roughly costs. Pure, so it runs in tests.
import type { Usage } from '../../../watchdog/src/logic.js';

export interface TypeUsage {
	/** "cx33", or "unknown" (a VPS still starting, or a month counted before types were). */
	type: string;
	hours: number;
	/** Euros per hour, or null when wrangler.toml has no price for this type. */
	price: number | null;
}

export interface MonthUsage {
	/** "November 2026". */
	label: string;
	hours: number;
	/** Most hours first. */
	types: TypeUsage[];
	/** Euros for the hours that have a price, or null when none do. */
	cost: number | null;
	/** Hours without a price (an unknown type, or one missing from wrangler.toml). */
	unpricedHours: number;
	/** Unix seconds when counting started, when that was after the month began. */
	countedSince: number | null;
}

export function monthUsage(usage: Usage | null, monthStart: Date, prices: Record<string, number>): MonthUsage {
	const minutes: Record<string, number> = { ...usage?.by_type };
	// Minutes counted before the watchdog recorded types have no type.
	const typed = Object.values(minutes).reduce((sum, m) => sum + m, 0);
	const untyped = (usage?.minutes ?? 0) - typed;
	if (untyped > 0) minutes.unknown = (minutes.unknown ?? 0) + untyped;

	const types = Object.entries(minutes)
		.filter(([, m]) => m > 0)
		.map(([type, m]) => ({ type, hours: m / 60, price: prices[type] ?? null }))
		.sort((a, b) => b.hours - a.hours);
	const priced = types.filter((t) => t.price !== null);
	const begins = monthStart.getTime() / 1000;
	return {
		label: monthStart.toLocaleString('en-GB', { month: 'long', year: 'numeric', timeZone: 'UTC' }),
		hours: (usage?.minutes ?? 0) / 60,
		types,
		cost: priced.length ? priced.reduce((sum, t) => sum + t.hours * (t.price as number), 0) : null,
		unpricedHours: types.filter((t) => t.price === null).reduce((sum, t) => sum + t.hours, 0),
		// More than a check after the month began: the watchdog started counting late.
		countedSince: usage && usage.since > begins + 600 ? usage.since : null
	};
}

/** The prices that are positive numbers; anything else counts as no price. */
export function parsePrices(value: unknown): Record<string, number> {
	if (!value || typeof value !== 'object') return {};
	return Object.fromEntries(
		Object.entries(value).filter(([, price]) => typeof price === 'number' && Number.isFinite(price) && price > 0)
	) as Record<string, number>;
}

/** The first moments of this UTC month and the one before. */
export function months(now: Date): [Date, Date] {
	const year = now.getUTCFullYear();
	const month = now.getUTCMonth();
	return [new Date(Date.UTC(year, month, 1)), new Date(Date.UTC(year, month - 1, 1))];
}
