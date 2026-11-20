import { expect, test } from 'vitest';
import { BOARDS, boards, top, type PlayerTotals } from './leaderboard';

const player = (name: string, values: Partial<PlayerTotals>): PlayerTotals => ({
	uuid: `uuid-${name}`,
	name,
	play_hours: 0,
	distance_km: 0,
	elytra_km: 0,
	mined: 0,
	mob_kills: 0,
	deaths: 0,
	...values
});

const players = [
	player('alice', { play_hours: 12.5, mined: 300, placed: 40 }),
	player('bob', { play_hours: 30, mined: 300 }),
	player('carol', { play_hours: 2, mined: 10, placed: 900 })
];

test('highest first, nobody with nothing', () => {
	expect(top(players, 'play_hours').map((e) => [e.rank, e.name])).toEqual([
		[1, 'bob'],
		[2, 'alice'],
		[3, 'carol']
	]);
	expect(top(players, 'deaths')).toEqual([]);
});

test('equal values share a rank, then go by name', () => {
	expect(top(players, 'mined').map((e) => [e.rank, e.name])).toEqual([
		[1, 'alice'],
		[1, 'bob'],
		[3, 'carol']
	]);
});

test('a missing value counts as nothing', () => {
	expect(top(players, 'placed').map((e) => e.name)).toEqual(['carol', 'alice']);
});

test('limit', () => {
	expect(top(players, 'play_hours', 2)).toHaveLength(2);
});

test('empty boards are left out', () => {
	const shown = boards({ updated: 0, players }).map((b) => b.stat);
	expect(shown).toEqual(['play_hours', 'placed', 'mined']);
});

test('formats', () => {
	const format = (stat: string, value: number) => BOARDS.find((b) => b.stat === stat)!.format(value);
	expect(format('play_hours', 12.5)).toBe('12.5 h');
	expect(format('distance_km', 1234.56)).toBe('1,234.6 km');
	expect(format('mined', 12045)).toBe('12,045');
});
