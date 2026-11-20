// The server list ping over Node's TCP, for `npm run dev` only: there the
// SvelteKit server runs in Node, which has no `cloudflare:sockets`. The deployed
// Worker uses serverStatus() from watchdog/src/minecraft.js.
import { connect } from 'node:net';
import { parseStatusDetails, statusRequest, type ServerStatus } from '../../../../watchdog/src/logic.js';

export function nodeServerStatus(address: string, host: string, port: number): Promise<ServerStatus | null> {
	return new Promise((resolve) => {
		let bytes = new Uint8Array(0);
		const socket = connect({ host: address, port });
		const done = (status: ServerStatus | null) => {
			socket.destroy();
			resolve(status);
		};
		socket.setTimeout(5000, () => done(null));
		socket.on('error', () => done(null));
		socket.on('connect', () => socket.write(statusRequest(host, port)));
		socket.on('data', (chunk: Buffer) => {
			const joined = new Uint8Array(bytes.length + chunk.length);
			joined.set(bytes);
			joined.set(chunk, bytes.length);
			bytes = joined;
			try {
				const status = parseStatusDetails(bytes);
				if (status) done(status);
			} catch {
				done(null);
			}
		});
	});
}
