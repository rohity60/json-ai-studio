import Link from 'next/link';
import type { BlogMeta } from '@/content/types';

export default function BlogCard({ m }: { m: BlogMeta }) {
  return (
    <Link
      href={`/blog/${m.slug}`}
      className="group flex flex-col rounded-xl border border-gray-200 bg-white p-5 transition-shadow hover:shadow-md"
    >
      <h3 className="text-base font-semibold text-gray-900 group-hover:text-purple-700">
        {m.title}
      </h3>
      <p className="mt-1 line-clamp-2 flex-1 text-sm text-gray-600">{m.description}</p>
      <div className="mt-3 flex items-center gap-2 text-xs text-gray-400">
        <span>{m.readingTime}</span>
        <span>·</span>
        <span>{new Date(m.updatedAt).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}</span>
      </div>
    </Link>
  );
}
