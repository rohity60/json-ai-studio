/** Read-only, syntax-lite JSON preview. Renders the raw JSON as text so it is
 *  crawlable (SEO) and needs no backend. Server component. */
export default function JsonPreview({ json }: { json: unknown }) {
  const text = JSON.stringify(json, null, 2);
  return (
    <pre className="max-h-[28rem] overflow-auto rounded-xl border border-gray-200 bg-gray-950 p-4 text-xs leading-relaxed text-gray-100">
      <code>{text}</code>
    </pre>
  );
}
