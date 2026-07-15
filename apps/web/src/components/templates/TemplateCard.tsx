import Link from 'next/link';
import DifficultyBadge from './DifficultyBadge';
import type { TemplateIndexItem } from '@/lib/templates';

export default function TemplateCard({ t }: { t: TemplateIndexItem }) {
  return (
    <Link
      href={`/templates/${t.slug}`}
      className="group flex flex-col rounded-xl border border-gray-200 bg-white p-4 transition-shadow hover:shadow-md"
    >
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-purple-600">
          {t.provider}
        </span>
        <DifficultyBadge difficulty={t.difficulty as any} />
      </div>
      <h3 className="text-base font-semibold text-gray-900 group-hover:text-purple-700">
        {t.title}
      </h3>
      <p className="mt-1 line-clamp-2 flex-1 text-sm text-gray-600">{t.description}</p>
      <div className="mt-3 flex flex-wrap gap-1">
        {t.tags.slice(0, 4).map((tag) => (
          <span key={tag} className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">
            {tag}
          </span>
        ))}
      </div>
    </Link>
  );
}
