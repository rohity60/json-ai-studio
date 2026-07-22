'use client';

import { useEffect } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import { trackEvent, reportConversion } from '@/lib/gtagConversion';

// Page-view Ads conversion action (separate label from the CTA-click conversion
// so counts don't overlap). Injected from the secrets manager. No-op until set.
const PAGEVIEW_LABEL = process.env.NEXT_PUBLIC_GTAG_PAGEVIEW_CONVERSION_LABEL;

// Fires on every page view. Next <Link> nav is soft (no full reload), so
// gtag('config') only sends the initial page_view — this covers subsequent
// navigations. App Router has no router.events; the usePathname/useSearchParams
// hooks are the idiomatic route-change signal.
//
// - page_view event: only on client navigations (the initial hard-load view is
//   already sent by gtag config, so skip it to avoid a double analytics hit).
// - page-view conversion: on the initial load AND every navigation, since the
//   conversion action is separate from config's page_view and must be fired
//   explicitly each time.
export default function PageViewTracker() {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  useEffect(() => {
    const query = searchParams?.toString();
    const page_path = query ? `${pathname}?${query}` : pathname;

    const w = window as unknown as { __gtagPvInit?: boolean };
    const isInitial = !w.__gtagPvInit;
    w.__gtagPvInit = true;

    // Skip the initial page_view analytics hit (config already sent it); still
    // count it as a conversion below.
    if (!isInitial) {
      trackEvent('page_view', { page_path, page_location: window.location.href });
    }

    reportConversion({ sendTo: PAGEVIEW_LABEL });
  }, [pathname, searchParams]);

  return null;
}
