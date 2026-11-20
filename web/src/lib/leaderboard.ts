// leaderboard.json, written on the VPS by scripts/leaderboard.py, and the
// boards the public page shows. Pure, so it runs in tests.

export interface PlayerTotals {
	uuid: string;
	name: string;
	play_hours: number;
	distance_km: number;
	elytra_km: number;
	mined: number;
	mob_kills: number;
	deaths: number;
	/** From Ledger; missing when the server had no Ledger log. */
	placed?: number;
}

export interface Leaderboard {
	/** Unix seconds when the VPS wrote it (at a start or stop). */
	updated: number;
	players: PlayerTotals[];
}

type Stat = Exclude<keyof PlayerTotals, 'uuid' | 'name'>;

export interface Board {
	stat: Stat;
	title: string;
	/** How a value reads: "12.5 h", "3.2 km", "1,204". */
	format: (value: number) => string;
}

const count = (value: number) => value.toLocaleString('en-GB');
const decimals = (digits: number, unit: string) => (value: number) =>
	`${value.toLocaleString('en-GB', { minimumFractionDigits: digits, maximumFractionDigits: digits })} ${unit}`;

export const BOARDS: Board[] = [
	{ stat: 'play_hours', title: 'Playtime', format: decimals(1, 'h') },
	{ stat: 'distance_km', title: 'Distance travelled', format: decimals(1, 'km') },
	{ stat: 'elytra_km', title: 'Flown with elytra', format: decimals(1, 'km') },
	{ stat: 'placed', title: 'Blocks placed', format: count },
	{ stat: 'mined', title: 'Blocks mined', format: count },
	{ stat: 'mob_kills', title: 'Mobs killed', format: count },
	{ stat: 'deaths', title: 'Deaths', format: count }
];

export interface Entry {
	rank: number;
	uuid: string;
	name: string;
	value: number;
}

/**
 * The top `limit` players on one stat, highest first. Players with nothing
 * (0, or no value) aren't listed; equal values share a rank.
 */
export function top(players: PlayerTotals[], stat: Stat, limit = 10): Entry[] {
	const sorted = players
		.map((p) => ({ uuid: p.uuid, name: p.name, value: p[stat] ?? 0 }))
		.filter((p) => p.value > 0)
		.sort((a, b) => b.value - a.value || a.name.localeCompare(b.name));
	const entries: Entry[] = [];
	sorted.slice(0, limit).forEach((p, i) => {
		const rank = i > 0 && entries[i - 1].value === p.value ? entries[i - 1].rank : i + 1;
		entries.push({ rank, ...p });
	});
	return entries;
}

/** The boards that have at least one entry (no "Blocks placed" without Ledger). */
export function boards(leaderboard: Leaderboard, limit = 10) {
	return BOARDS.map((board) => ({ ...board, entries: top(leaderboard.players, board.stat, limit) })).filter(
		(board) => board.entries.length > 0
	);
}
