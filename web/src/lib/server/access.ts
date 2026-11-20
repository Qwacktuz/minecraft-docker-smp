// Cloudflare Access sits in front of /admin and blocks anyone not on its
// allow-list. This checks its signed header too, so a request that reached
// the Worker some other way (e.g. a misconfigured route) is still refused.
import { createRemoteJWKSet, jwtVerify } from 'jose';

const keySets = new Map<string, ReturnType<typeof createRemoteJWKSet>>();

/** The signed-in admin's email, or null when the request has no valid Access token. */
export async function accessEmail(
	request: Request,
	env: { ACCESS_TEAM_DOMAIN: string; ACCESS_AUD: string }
): Promise<string | null> {
	const token = request.headers.get('cf-access-jwt-assertion');
	if (!token || env.ACCESS_AUD.startsWith('REPLACE_')) return null;
	const issuer = `https://${env.ACCESS_TEAM_DOMAIN}`;
	let keys = keySets.get(issuer);
	if (!keys) {
		keys = createRemoteJWKSet(new URL(`${issuer}/cdn-cgi/access/certs`));
		keySets.set(issuer, keys);
	}
	try {
		const { payload } = await jwtVerify(token, keys, { issuer, audience: env.ACCESS_AUD });
		return typeof payload.email === 'string' ? payload.email : null;
	} catch {
		return null;
	}
}
