'use client';

import { SWRConfig } from 'swr';

/** useUser() (@auth0/nextjs-auth0) fetches /auth/profile through SWR, whose
 *  defaults refetch on every window focus, reconnect and component remount.
 *  The profile only changes on login/logout, which are full page loads, so
 *  load it once per page and never revalidate or retry in the background. */
export default function AuthSWRConfig({ children }: { children: React.ReactNode }) {
  return (
    <SWRConfig
      value={{
        revalidateOnFocus: false,
        revalidateOnReconnect: false,
        revalidateIfStale: false,
        shouldRetryOnError: false,
      }}
    >
      {children}
    </SWRConfig>
  );
}
