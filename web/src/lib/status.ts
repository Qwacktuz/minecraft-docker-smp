// What the status page shows, from the live ping and the watchdog's state.
// Pure, so it runs in tests; the Worker side is in server/status.ts.
import type { WatchdogState } from '../../../watchdog/src/logic.js';

export interface Status {
	/** 'off': no VPS. 'starting': VPS exists but the game doesn't answer. 'online': it answers. */
	state: 'off' | 'starting' | 'online';
	players: number | null;
	/** Unix seconds, or null when unknown. */
	upSince: number | null;
	lastBusy: number | null;
	/** Unix seconds when the watchdog will stop the VPS if nothing changes. */
	stopAt: number | null;
	stopReason: 'idle' | 'max-uptime' | null;
	checked: number;
}

export function describe(
	address: string | null,
	online: number | null,
	state: WatchdogState,
	now: number,
	{ idleMinutes, maxDays }: { idleMinutes: number; maxDays: number }
): Status {
	if (address === null) {
		return { state: 'off', players: null, upSince: null, lastBusy: null, stopAt: null, stopReason: null, checked: now };
	}
	// The watchdog's state belongs to an older VPS when the address changed.
	const known = state.address === address;
	const upSince = known ? (state.up_since ?? null) : null;
	const lastBusy = online ? now : known ? (state.last_busy ?? null) : null;
	const idleStop = online ? null : lastBusy === null ? null : lastBusy + idleMinutes * 60;
	const capStop = upSince === null ? null : upSince + maxDays * 86400;
	let stopAt: number | null = null;
	let stopReason: Status['stopReason'] = null;
	if (idleStop !== null && (capStop === null || idleStop <= capStop)) {
		stopAt = idleStop;
		stopReason = 'idle';
	} else if (capStop !== null) {
		stopAt = capStop;
		stopReason = 'max-uptime';
	}
	return {
		state: online === null ? 'starting' : 'online',
		players: online,
		upSince,
		lastBusy,
		stopAt,
		stopReason,
		checked: now
	};
}

/** "3 h 5 min", "12 min", "2 d 4 h": a rough duration in seconds. */
export function duration(seconds: number): string {
	const s = Math.max(0, Math.round(seconds));
	const d = Math.floor(s / 86400);
	const h = Math.floor((s % 86400) / 3600);
	const m = Math.floor((s % 3600) / 60);
	if (d) return h ? `${d} d ${h} h` : `${d} d`;
	if (h) return m ? `${h} h ${m} min` : `${h} h`;
	return `${m} min`;
}
