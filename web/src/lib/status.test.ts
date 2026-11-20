import { describe as group, expect, test } from 'vitest';
import { describe, duration } from './status';

const config = { idleMinutes: 120, maxDays: 14 };
const ip = '192.0.2.1';
const HOUR = 3600;

group('describe', () => {
	test('no DNS record: off', () => {
		expect(describe(null, null, { address: ip, up_since: 0 }, 100, config).state).toBe('off');
	});

	test('nobody online: auto-stop counts from the last busy time', () => {
		const s = describe(ip, 0, { address: ip, up_since: 0, last_busy: HOUR }, 2 * HOUR, config);
		expect(s.state).toBe('online');
		expect(s.stopAt).toBe(HOUR + 120 * 60);
		expect(s.stopReason).toBe('idle');
	});

	test('players online: only the uptime cap applies', () => {
		const s = describe(ip, 3, { address: ip, up_since: 0, last_busy: 0 }, 5 * HOUR, config);
		expect(s.players).toBe(3);
		expect(s.stopAt).toBe(14 * 86400);
		expect(s.stopReason).toBe('max-uptime');
	});

	test('the cap wins when it comes before the idle stop', () => {
		const upSince = 0;
		const now = 14 * 86400 - 10 * 60;
		const s = describe(ip, 0, { address: ip, up_since: upSince, last_busy: now }, now, config);
		expect(s.stopReason).toBe('max-uptime');
	});

	test('state from an older VPS is ignored', () => {
		const s = describe(ip, null, { address: '198.51.100.9', up_since: 0, last_busy: 0 }, 50, config);
		expect(s.state).toBe('starting');
		expect(s.upSince).toBeNull();
		expect(s.stopAt).toBeNull();
	});
});

test('duration', () => {
	expect(duration(59)).toBe('0 min');
	expect(duration(125 * 60)).toBe('2 h 5 min');
	expect(duration(2 * 86400 + 4 * HOUR)).toBe('2 d 4 h');
	expect(duration(-5)).toBe('0 min');
});
