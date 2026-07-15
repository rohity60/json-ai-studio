'use client';

import { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import TemplateCard from './TemplateCard';
import type { TemplateIndexItem } from '@/lib/templates';

interface Facets {
  categories: string[];
  providers: string[];
  difficulties: string[];
}

const ALL = 'All';

export default function TemplateExplorer({
  index,
  facets,
}: {
  index: TemplateIndexItem[];
  facets: Facets;
}) {
  const [q, setQ] = useState('');
  const [category, setCategory] = useState(ALL);
  const [provider, setProvider] = useState(ALL);
  const [difficulty, setDifficulty] = useState(ALL);

  const results = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return index.filter((t) => {
      if (category !== ALL && t.category !== category) return false;
      if (provider !== ALL && t.provider !== provider) return false;
      if (difficulty !== ALL && t.difficulty !== difficulty) return false;
      if (!needle) return true;
      const hay = `${t.title} ${t.description} ${t.provider} ${t.category} ${t.tags.join(' ')}`.toLowerCase();
      return hay.includes(needle);
    });
  }, [index, q, category, provider, difficulty]);

  const select = (
    value: string,
    onChange: (v: string) => void,
    options: string[],
    label: string,
  ) => (
    <select
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm capitalize text-gray-700"
    >
      <option value={ALL}>{label}: All</option>
      {options.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  );

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search templates (aws, docker, jwt, openapi…)"
            className="w-full rounded-lg border border-gray-200 bg-white py-2 pl-9 pr-3 text-sm"
          />
        </div>
        {select(category, setCategory, facets.categories, 'Category')}
        {select(provider, setProvider, facets.providers, 'Provider')}
        {select(difficulty, setDifficulty, facets.difficulties, 'Difficulty')}
      </div>

      <p className="mb-3 text-sm text-gray-500">
        {results.length} template{results.length === 1 ? '' : 's'}
      </p>

      {results.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-300 p-10 text-center text-sm text-gray-500">
          No templates match your filters.
          <button
            onClick={() => {
              setQ('');
              setCategory(ALL);
              setProvider(ALL);
              setDifficulty(ALL);
            }}
            className="ml-1 text-purple-600 hover:underline"
          >
            Clear filters
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {results.map((t) => (
            <TemplateCard key={t.slug} t={t} />
          ))}
        </div>
      )}
    </div>
  );
}
