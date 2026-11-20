// Types for logic.js, for the web app's TypeScript (web/). The Worker ignores this file.
export interface WatchdogState {
  address?: string;
  up_since?: number;
  last_busy?: number;
  last_dispatch?: number;
}

export function varint(n: number): number[];
export function readVarint(bytes: Uint8Array, offset: number): [number, number] | null;
export function statusRequest(host: string, port: number): Uint8Array;
export function parseStatus(bytes: Uint8Array): number | null;
export function decide(
  previous: WatchdogState,
  address: string | null,
  online: number | null,
  now: number,
  config: { idleMinutes: number; maxDays: number },
): { stop: boolean; reason: string; state: WatchdogState };
export function shouldDispatch(state: WatchdogState, runsInFlight: number, now: number, cooldownMinutes?: number): boolean;
