import { describe as group, expect, test } from 'vitest';
import { current, disk, heap, memory, place, summary, type Vps } from './vps';

const vps: Vps = {
	updated: 0,
	type: 'cx33',
	location: 'hel1',
	ipv4: '192.0.2.1',
	arch: 'x86_64',
	cpus: 4,
	cpu_model: 'AMD EPYC',
	memory_bytes: 7.6 * 2 ** 30, // what an 8 GB VPS reports
	disk_bytes: 78e9,
	heap: '5G'
};

group('vps', () => {
	test('summary', () => {
		expect(summary(vps)).toBe('Hetzner CX33 · 4 vCPU · 8 GB RAM');
	});

	test('sizes round like Hetzner advertises them', () => {
		expect(memory(vps.memory_bytes)).toBe('8 GB');
		expect(disk(vps.disk_bytes)).toBe('78 GB');
		expect(heap('5G')).toBe('5 GB');
		expect(heap('512M')).toBe('512 MB');
	});

	test('places', () => {
		expect(place('fsn1')).toBe('Falkenstein (fsn1)');
		expect(place('xyz9')).toBe('xyz9');
	});

	test('only the VPS that DNS points at counts', () => {
		expect(current(vps, '192.0.2.1')).toBe(vps);
		expect(current(vps, '192.0.2.99')).toBeNull();
		expect(current(vps, null)).toBeNull();
		expect(current(null, '192.0.2.1')).toBeNull();
	});
});
