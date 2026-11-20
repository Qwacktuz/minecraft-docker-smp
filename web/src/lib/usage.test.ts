import { expect, test } from 'vitest';
import { monthUsage, months, parsePrices } from './usage';

const november = new Date(Date.UTC(2026, 10, 1));
const begins = november.getTime() / 1000;
const prices = { cx33: 0.01, cpx32: 0.02 };

test('cost adds up each type at its own price', () => {
	const usage = monthUsage({ since: begins + 60, minutes: 180, by_type: { cx33: 120, cpx32: 60 } }, november, prices);
	expect(usage.label).toBe('November 2026');
	expect(usage.hours).toBe(3);
	expect(usage.types.map((t) => [t.type, t.hours])).toEqual([['cx33', 2], ['cpx32', 1]]);
	expect(usage.cost).toBeCloseTo(2 * 0.01 + 1 * 0.02);
	expect(usage.unpricedHours).toBe(0);
	expect(usage.countedSince).toBeNull();
});

test('hours of an unknown or unpriced type are left out of the cost', () => {
	const usage = monthUsage({ since: begins, minutes: 240, by_type: { cx33: 60, unknown: 60, cax21: 120 } }, november, prices);
	expect(usage.cost).toBeCloseTo(0.01);
	expect(usage.unpricedHours).toBe(3);
});

test('minutes counted before types were count as unknown', () => {
	const usage = monthUsage({ since: begins, minutes: 90, by_type: { cx33: 30 } }, november, prices);
	expect(usage.types).toEqual([
		{ type: 'unknown', hours: 1, price: null },
		{ type: 'cx33', hours: 0.5, price: 0.01 }
	]);
	expect(monthUsage({ since: begins, minutes: 60 }, november, prices).unpricedHours).toBe(1);
});

test('no prices at all: no cost', () => {
	const usage = monthUsage({ since: begins, minutes: 60, by_type: { cx33: 60 } }, november, {});
	expect(usage.cost).toBeNull();
	expect(usage.unpricedHours).toBe(1);
});

test('a month the watchdog started counting late says since when', () => {
	const since = begins + 19 * 86400;
	expect(monthUsage({ since, minutes: 5 }, november, prices).countedSince).toBe(since);
	expect(monthUsage(null, november, prices)).toMatchObject({ hours: 0, types: [], cost: null });
});

test('only positive numbers are prices', () => {
	expect(parsePrices({ cx33: 0.0104, cpx32: 0, cax21: 'x', ccx13: -1 })).toEqual({ cx33: 0.0104 });
	expect(parsePrices(undefined)).toEqual({});
	expect(parsePrices('0.01')).toEqual({});
});

test('this month and the one before, across a new year', () => {
	const [current, previous] = months(new Date(Date.UTC(2027, 0, 15)));
	expect(current.toISOString()).toBe('2027-01-01T00:00:00.000Z');
	expect(previous.toISOString()).toBe('2026-12-01T00:00:00.000Z');
});
