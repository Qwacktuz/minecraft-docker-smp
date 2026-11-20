import { expect, test } from 'vitest';
import { monthUsage, months, parsePrice } from './usage';

const november = new Date(Date.UTC(2026, 10, 1));
const begins = november.getTime() / 1000;

test('hours and cost', () => {
	const usage = monthUsage({ since: begins + 60, minutes: 150 }, november, 0.02);
	expect(usage.label).toBe('November 2026');
	expect(usage.hours).toBe(2.5);
	expect(usage.cost).toBeCloseTo(0.05);
	expect(usage.countedSince).toBeNull();
});

test('a month the watchdog started counting late says since when', () => {
	const since = begins + 19 * 86400;
	expect(monthUsage({ since, minutes: 5 }, november, null).countedSince).toBe(since);
});

test('no usage and no price', () => {
	expect(monthUsage(null, november, null)).toMatchObject({ hours: 0, cost: null, countedSince: null });
});

test('prices', () => {
	expect(parsePrice('0.0104')).toBe(0.0104);
	expect(parsePrice('')).toBeNull();
	expect(parsePrice('abc')).toBeNull();
	expect(parsePrice(undefined)).toBeNull();
});

test('this month and the one before, across a new year', () => {
	const [current, previous] = months(new Date(Date.UTC(2027, 0, 15)));
	expect(current.toISOString()).toBe('2027-01-01T00:00:00.000Z');
	expect(previous.toISOString()).toBe('2026-12-01T00:00:00.000Z');
});
