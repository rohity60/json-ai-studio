import Link from 'next/link';
import { getRelatedTemplates } from '@/lib/templates';
import { getRelatedPosts } from '@/lib/blog';

export default function RelatedLists({
  templates,
  blogs,
}: {
  templates: string[];
  blogs: string[];
}) {
  const tpls = getRelatedTemplates(templates);
  const posts = getRelatedPosts(blogs);
  if (!tpls.length && !posts.length) return null;

  return (
    <div className="grid gap-6 sm:grid-cols-2">
      {tpls.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-gray-900">Related templates</h3>
          <ul className="space-y-1 text-sm">
            {tpls.map((m) => (
              <li key={m.slug}>
                <Link href={`/templates/${m.slug}`} className="text-purple-600 hover:underline">
                  {m.title}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
      {posts.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold text-gray-900">Related articles</h3>
          <ul className="space-y-1 text-sm">
            {posts.map((m) => (
              <li key={m.slug}>
                <Link href={`/blog/${m.slug}`} className="text-purple-600 hover:underline">
                  {m.title}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
