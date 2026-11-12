import { Auth0Client } from '@auth0/nextjs-auth0/server';

// Reads AUTH0_DOMAIN / AUTH0_CLIENT_ID / AUTH0_CLIENT_SECRET / AUTH0_SECRET /
// APP_BASE_URL from env. The audience must match an Auth0 API identifier or
// access tokens come back opaque and fail backend JWT validation (ADR-0015).
//
// Anonymous visitors: /auth/profile answers 204 instead of 401. useUser()
// (SWR) treats 401 as an error and retries with backoff + on every focus,
// polling the endpoint forever; 204 resolves to user = null with no retry.
export const auth0 = new Auth0Client({
    noContentProfileResponseWhenUnauthenticated: true,
    authorizationParameters: {
        audience: process.env.AUTH0_AUDIENCE,
        scope: process.env.AUTH0_SCOPE || 'openid profile email',
    },
});
