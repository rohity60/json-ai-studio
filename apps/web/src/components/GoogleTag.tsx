// Google tag (gtag.js) for Google Ads / GA. The config ID is injected at
// build/runtime from the secrets manager as NEXT_PUBLIC_GTAG_ID. It is a public
// value (it ships to the browser), so NEXT_PUBLIC_ is required. Renders nothing
// when unset so local/dev builds without the secret stay clean.
//
// Deliberately plain <script> tags, NOT next/script: this is a server component,
// so these render statically into the SSR <head>. next/script's afterInteractive
// strategy injects client-side after hydration and is therefore invisible to
// Google's tag verifier / crawlers that read raw server HTML.
export default function GoogleTag() {
  const id = process.env.NEXT_PUBLIC_GTAG_ID;
  if (!id) return null;

  return (
    <>
      <script async src={`https://www.googletagmanager.com/gtag/js?id=${id}`} />
      <script
        dangerouslySetInnerHTML={{
          __html: `
            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}
            gtag('js', new Date());
            gtag('config', '${id}');
          `,
        }}
      />
    </>
  );
}
