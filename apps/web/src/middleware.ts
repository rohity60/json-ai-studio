import { NextResponse, type NextRequest } from 'next/server';

// Auth0 middleware mounts /auth/login, /auth/logout, /auth/callback,
// /auth/profile, /auth/access-token. When Auth0 env vars are absent the
// app degrades to anonymous-only mode (mirrors the backend, ADR-0015).
export async function middleware(request: NextRequest) {
    if (!process.env.AUTH0_DOMAIN || !process.env.AUTH0_CLIENT_ID) {
        return NextResponse.next();
    }
    const { auth0 } = await import('./lib/auth0');
    return auth0.middleware(request);
}

export const config = {
    matcher: [
        '/((?!_next/static|_next/image|favicon.ico|icon.svg|sitemap.xml|robots.txt|llms.txt|llms-full.txt).*)',
    ],
};
