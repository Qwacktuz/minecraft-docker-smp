// vps.json and players.json, written on the VPS by scripts/publish-status.sh
// (scripts/web_status.py), and how the pages show them. Pure, so it runs in tests.

export interface Vps {
	/** Unix seconds when the VPS wrote it (at the end of a start). */
	updated: number;
	/** Hetzner server type, e.g. "cx33". */
	type: string;
	/** Hetzner location, e.g. "hel1". */
	location: string;
	/** The VPS's IPv4 address: the pages only trust this file while DNS points there. */
	ipv4: string;
	arch: string;
	cpus: number;
	cpu_model: string | null;
	memory_bytes: number;
	disk_bytes: number;
	/** The game's heap (MEMORY in compose.yml), e.g. "5G". */
	heap: string | null;
}

export interface Player {
	name: string;
	uuid: string;
	whitelisted: boolean;
	/** 1-4 for ops, null for everyone else. */
	op_level: number | null;
}

export interface Players {
	updated: number;
	players: Player[];
}

const LOCATIONS: Record<string, string> = {
	hel1: 'Helsinki',
	fsn1: 'Falkenstein',
	nbg1: 'Nuremberg',
	ash: 'Ashburn',
	hil: 'Hillsboro',
	sin: 'Singapore'
};

/** "Helsinki (hel1)", or just the code for a location this list doesn't know. */
export function place(location: string): string {
	const city = LOCATIONS[location];
	return city ? `${city} (${location})` : location;
}

/** RAM in whole GB, the way Hetzner advertises it: the kernel reports a little less. */
export function memory(bytes: number): string {
	return `${Math.round(bytes / 2 ** 30)} GB`;
}

/** Disk size in GB (decimal, like Hetzner's plans). */
export function disk(bytes: number): string {
	return `${Math.round(bytes / 1e9)} GB`;
}

/** The JVM's "5G" or "512M" as "5 GB" or "512 MB". */
export function heap(value: string): string {
	return value.replace(/^(\d+)([GM])$/i, (_, n, unit) => `${n} ${unit.toUpperCase()}B`);
}

/** "Hetzner CX33 · 4 vCPU · 8 GB RAM". */
export function summary(vps: Pick<Vps, 'type' | 'cpus' | 'memory_bytes'>): string {
	return `Hetzner ${vps.type.toUpperCase()} · ${vps.cpus} vCPU · ${memory(vps.memory_bytes)} RAM`;
}

/** The published file when it describes the VPS that DNS points at now, else null. */
export function current(vps: Vps | null, address: string | null): Vps | null {
	return vps && address && vps.ipv4 === address ? vps : null;
}
