import Script from 'next/script';

// Google tag (gtag.js) for Google Ads / GA. The config ID is injected at
// build/runtime from the secrets manager as NEXT_PUBLIC_GTAG_ID. It is a public
// value (it ships to the browser), so NEXT_PUBLIC_ is required. Renders nothing
// when unset so local/dev builds without the secret stay clean.
export default function GoogleTag() {
  const id = process.env.NEXT_PUBLIC_GTAG_ID;
  if (!id) return null;

  return (
    <>
      <Script
        id="gtag-src"
        strategy="afterInteractive"
        src={`https://www.googletagmanager.com/gtag/js?id=${id}`}
      />
      <Script id="gtag-init" strategy="afterInteractive">
        {`
          window.dataLayer = window.dataLayer || [];
          function gtag(){dataLayer.push(arguments);}
          gtag('js', new Date());
          gtag('config', '${id}');
        `}
      </Script>
    </>
  );
}
