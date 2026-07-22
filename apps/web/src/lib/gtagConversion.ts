// Sends a named gtag event (page_view, chat_submit, json_upload, ...). Distinct
// from reportConversion so activation signals don't inflate any Ads conversion
// count. No-op when gtag isn't loaded. To promote an event to an Ads conversion,
// create the conversion action in Google Ads and fire reportConversion with its
// label instead.
export function trackEvent(name: string, params: Record<string, unknown> = {}): void {
  const gtag = (window as unknown as { gtag?: (...args: unknown[]) => void }).gtag;
  if (typeof gtag !== 'function') return;
  gtag('event', name, params);
}

// Fires a Google Ads conversion. The send_to label (e.g. "AW-XXXXXXXXXX/AbC123")
// defaults to the CTA-click label (NEXT_PUBLIC_GTAG_CONVERSION_LABEL, injected
// from the secrets manager) but callers can pass a different label — page views
// use their own action so counts stay separate. No-op when gtag isn't loaded or
// the label is unset, so dev/local builds without the secret stay clean.
//
// Pass a url to navigate AFTER the conversion beacon (mirrors Google's
// gtag_report_conversion snippet — used for full-page links). Internal Next
// <Link> CTAs omit url: Link handles navigation, we just fire the beacon.
export function reportConversion(
  opts: { sendTo?: string; url?: string } = {},
): boolean {
  const sendTo = opts.sendTo ?? process.env.NEXT_PUBLIC_GTAG_CONVERSION_LABEL;
  const url = opts.url;
  const gtag = (window as unknown as { gtag?: (...args: unknown[]) => void }).gtag;

  if (!sendTo || typeof gtag !== 'function') {
    if (url) window.location.href = url;
    return false;
  }

  const callback = () => {
    if (url) window.location.href = url;
  };

  gtag('event', 'conversion', {
    send_to: sendTo,
    value: 1.0,
    currency: 'INR',
    event_callback: callback,
  });

  return false;
}
