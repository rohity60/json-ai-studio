import type { FaqItem } from '@/content/types';

export default function Faq({ items }: { items: FaqItem[] }) {
  if (!items?.length) return null;
  return (
    <section className="mt-10 border-t border-gray-200 pt-6">
      <h2 className="mb-4 text-lg font-semibold text-gray-900">FAQ</h2>
      <div className="space-y-4">
        {items.map((f, i) => (
          <details key={i} className="rounded-lg border border-gray-200 p-4">
            <summary className="cursor-pointer text-sm font-medium text-gray-900">
              {f.q}
            </summary>
            <p className="mt-2 text-sm leading-relaxed text-gray-600">{f.a}</p>
          </details>
        ))}
      </div>
    </section>
  );
}
