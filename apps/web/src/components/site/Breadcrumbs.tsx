import Link from 'next/link';

export default function Breadcrumbs({ crumbs }: { crumbs: { name: string; path: string }[] }) {
  return (
    <nav aria-label="Breadcrumb" className="mb-4 text-sm text-gray-500">
      <ol className="flex flex-wrap items-center gap-1">
        {crumbs.map((c, i) => (
          <li key={c.path} className="flex items-center gap-1">
            {i < crumbs.length - 1 ? (
              <Link href={c.path} className="hover:text-purple-700">
                {c.name}
              </Link>
            ) : (
              <span className="text-gray-700">{c.name}</span>
            )}
            {i < crumbs.length - 1 && <span className="text-gray-300">/</span>}
          </li>
        ))}
      </ol>
    </nav>
  );
}
