// backups.json in the WEB bucket, written on the VPS by scripts/publish-status.sh
// at every start and stop (restic can't run in a Worker).
import type { Env } from './env';
export interface Snapshot {
	id: string;
	time: number;
	tags: string[];
}

export interface Backups {
	/** Unix seconds when the list was written. */
	updated: number;
	snapshots: Snapshot[];
}

export async function getBackups(env: Env): Promise<Backups | null> {
	const object = await env.WEB.get('backups.json');
	return object ? ((await object.json()) as Backups) : null;
}
