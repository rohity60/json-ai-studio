'use client';

import { useEffect } from 'react';
import { reportConversion } from '@/lib/gtagConversion';

// Global delegated click listener. Fires the Google Ads conversion whenever a
// primary CTA (marked with data-gtag-conversion) is clicked, on any page.
// Mounted once in the root layout so it covers every route. Fire-and-forget:
// tagged CTAs are Next <Link>s that navigate themselves, so we only send the
// beacon and never block navigation. Capture phase ensures it runs before
// Link's own click handling.
export default function ConversionTracker() {
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement | null;
      if (target?.closest?.('[data-gtag-conversion]')) {
        reportConversion();
      }
    };
    document.addEventListener('click', onClick, true);
    return () => document.removeEventListener('click', onClick, true);
  }, []);

  return null;
}
