/** Client-side Auth0 access-token cache.
 *
 *  getAccessToken() round-trips to /auth/access-token (refreshing via the
 *  encrypted session cookie), so cache the token in module scope and only
 *  re-fetch within 60s of expiry. Returns null when not logged in — callers
 *  fall back to the anonymous X-API-Key path.
 */

import { getAccessToken } from '@auth0/nextjs-auth0';

let cached: { token: string; exp: number } | null = null;

function decodeExp(token: string): number {
    try {
        return JSON.parse(atob(token.split('.')[1])).exp ?? 0;
    } catch {
        return 0;
    }
}

export async function getBearerToken(): Promise<string | null> {
    if (cached && cached.exp - 60 > Date.now() / 1000) return cached.token;
    try {
        const token = await getAccessToken();
        if (!token) {
            cached = null;
            return null;
        }
        cached = { token, exp: decodeExp(token) };
        return token;
    } catch {
        cached = null;
        return null; // not logged in → anonymous
    }
}

export function clearBearerToken() {
    cached = null;
}
