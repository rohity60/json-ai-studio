// Renders a schema.org JSON-LD <script> for AI crawlers and search engines.
// Server component — the payload is static app content, so JSON.stringify is safe.
export default function JsonLd({ data }: { data: Record<string, unknown> }) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }}
    />
  );
}
