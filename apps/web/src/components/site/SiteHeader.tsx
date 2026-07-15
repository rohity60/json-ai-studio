import Link from 'next/link';
import Logo from '@/components/Logo';

const REPO_URL = 'https://github.com/rohity60/json-ai-studio';

const NAV = [
  { label: 'Home', href: '/' },
  { label: 'Workspace', href: '/studio' },
  { label: 'Templates', href: '/templates' },
  { label: 'Blog', href: '/blog' },
];

/** Shared top nav for the hub pages (templates/blog). The landing page keeps
 *  its own richer header; these links mirror the target order in PRD §3. */
export default function SiteHeader() {
  return (
    <header className="sticky top-0 z-20 border-b border-gray-200 bg-white/80 backdrop-blur">
      <div className="flex h-14 items-center justify-between px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2">
          <Logo />
        </Link>
        <nav className="flex items-center gap-1 text-sm">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className="rounded-lg px-3 py-1.5 text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900"
            >
              {n.label}
            </Link>
          ))}
          <a
            href={REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-1 rounded-lg px-3 py-1.5 text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900"
          >
            GitHub
          </a>
        </nav>
      </div>
    </header>
  );
}
