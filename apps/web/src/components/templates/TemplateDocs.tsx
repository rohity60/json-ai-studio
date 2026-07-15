import type { TemplateMeta } from '@/content/types';

function List({ title, items }: { title: string; items: string[] }) {
  if (!items?.length) return null;
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-gray-900">{title}</h3>
      <ul className="list-disc space-y-1 pl-5 text-sm text-gray-600">
        {items.map((it, i) => (
          <li key={i}>{it}</li>
        ))}
      </ul>
    </div>
  );
}

function Para({ title, text }: { title: string; text: string }) {
  if (!text) return null;
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-gray-900">{title}</h3>
      <p className="text-sm leading-relaxed text-gray-600">{text}</p>
    </div>
  );
}

export default function TemplateDocs({ meta }: { meta: TemplateMeta }) {
  return (
    <div className="grid gap-6 sm:grid-cols-2">
      <Para title="Purpose" text={meta.purpose} />
      <Para title="When to use" text={meta.whenToUse} />
      <List title="Required fields" items={meta.requiredFields} />
      <List title="Optional fields" items={meta.optionalFields} />
      <List title="Best practices" items={meta.bestPractices} />
      <List title="Security considerations" items={meta.security} />
    </div>
  );
}
