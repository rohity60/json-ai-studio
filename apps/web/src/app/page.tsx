import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight, Check, X, Minus, Star, ChevronDown } from 'lucide-react';
import Logo from '@/components/Logo';
import JsonLd from '@/components/JsonLd';

const REPO_URL = 'https://github.com/rohity60/json-ai-studio';

// lucide-react (this project's pinned build) ships no GitHub brand icon, so use the official mark.
function Github({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" className={className}>
      <path d="M12 .5C5.37.5 0 5.87 0 12.5c0 5.3 3.44 9.8 8.21 11.39.6.11.82-.26.82-.58 0-.29-.01-1.04-.02-2.05-3.34.73-4.04-1.61-4.04-1.61-.55-1.39-1.34-1.76-1.34-1.76-1.09-.75.08-.73.08-.73 1.2.08 1.84 1.24 1.84 1.24 1.07 1.83 2.81 1.3 3.5.99.11-.78.42-1.3.76-1.6-2.67-.3-5.47-1.34-5.47-5.96 0-1.32.47-2.39 1.24-3.23-.12-.31-.54-1.53.12-3.18 0 0 1.01-.32 3.3 1.23a11.5 11.5 0 0 1 6.01 0c2.29-1.55 3.3-1.23 3.3-1.23.66 1.65.24 2.87.12 3.18.77.84 1.24 1.91 1.24 3.23 0 4.63-2.81 5.65-5.49 5.95.43.37.81 1.1.81 2.22 0 1.61-.01 2.9-.01 3.29 0 .32.22.7.83.58C20.56 22.29 24 17.8 24 12.5 24 5.87 18.63.5 12 .5z" />
    </svg>
  );
}

export const metadata: Metadata = {
  title: 'AI JSON Formatter & Editor — JSON AI Studio',
  description:
    'Format, explain, edit, validate and transform JSON using AI. Upload any JSON, describe changes in plain English, review every modification with side-by-side diffs, and download valid JSON with confidence.',
  keywords: [
    'ai json formatter',
    'ai json editor',
    'json editor',
    'json viewer',
    'json validator',
    'json diff',
    'json explain',
    'json formatter online',
    'ai json tool',
  ],
  alternates: { canonical: '/' },
  openGraph: {
    title: 'AI JSON Formatter & Editor — JSON AI Studio',
    description:
      'The complete AI-powered workspace for working with JSON. Format, explain, edit, validate and diff JSON in plain English.',
    url: '/',
    siteName: 'JSON AI Studio',
    type: 'website',
  },
};

async function getStars(): Promise<number | null> {
  try {
    const r = await fetch('https://api.github.com/repos/rohity60/json-ai-studio', {
      next: { revalidate: 3600 },
    });
    if (!r.ok) return null;
    const data = await r.json();
    return typeof data.stargazers_count === 'number' ? data.stargazers_count : null;
  } catch {
    return null;
  }
}

const features = [
  {
    emoji: '🧠',
    title: 'Explain JSON',
    copy: 'Instantly understand complex API responses, deeply nested JSON and unfamiliar structures. Instead of reading thousands of lines manually, ask AI questions about your JSON.',
  },
  {
    emoji: '✏️',
    title: 'Edit JSON with AI',
    copy: 'Describe changes in plain English. The AI modifies your JSON while preserving formatting and validity. No manual editing.',
  },
  {
    emoji: '🔍',
    title: 'Review Every Change',
    copy: 'Every AI modification is shown as a visual side-by-side diff. Accept only the changes you want.',
  },
  {
    emoji: '✅',
    title: 'Always Valid JSON',
    copy: 'Automatically validate syntax after every AI edit. Never download broken JSON.',
  },
  {
    emoji: '📂',
    title: 'Work with Large JSON Files',
    copy: 'Open and work with large API payloads and configuration files that are difficult to edit manually.',
  },
  {
    emoji: '🗂️',
    title: 'Workspaces & Versions',
    copy: 'Organize JSON into named workspaces, save tagged documents and keep a full version history — auto-saved and ready to resume when you log in.',
  },
];

const workflow = [
  { title: 'Upload JSON', copy: 'Drop in a file or paste raw JSON.' },
  { title: 'AI explains the structure', copy: 'Understand what you are looking at instantly.' },
  { title: 'Ask AI to modify it', copy: 'Describe the change in plain English.' },
  { title: 'Review side-by-side diff', copy: 'Accept only the changes you want.' },
  { title: 'Download valid JSON', copy: 'Export syntax-checked, valid JSON.' },
];

const useCases = [
  'Understand API Responses',
  'Modify Configuration Files',
  'Clean Messy JSON',
  'Generate JSON Explanations',
  'Debug Nested JSON',
  'Compare AI Changes',
  'Explore Unknown JSON',
  'Learn Third-party APIs',
];

// [label, JSON AI Studio, Traditional JSON Editors, General AI Chatbots]
// true = yes, false = no, 'partial' = limited
const comparison: [string, boolean, boolean | 'partial', boolean | 'partial'][] = [
  ['Purpose-built for JSON', true, true, false],
  ['Keeps JSON Valid', true, 'partial', false],
  ['Natural Language Editing', true, false, true],
  ['Side-by-side Diffs', true, 'partial', false],
  ['Version History', true, 'partial', false],
  ['Saved Workspaces', true, false, false],
  ['JSON Explanations', true, false, 'partial'],
  ['Large File Support', true, true, false],
  ['Visual Editing', true, true, false],
  ['Open Source', true, 'partial', false],
];

// Single source of truth for both the visible FAQ section and the FAQPage
// JSON-LD below — AI assistants get the same Q&A they can read on the page.
const faqs = [
  {
    q: 'What is JSON AI Studio?',
    a: 'JSON AI Studio is a free, AI-powered workspace for JSON. Upload or paste JSON, describe changes in plain English, review every edit as a side-by-side diff, and download valid JSON — plus AI explanations and full version history.',
  },
  {
    q: 'Is JSON AI Studio free?',
    a: 'Yes. The core JSON formatter, editor, explainer, validator and diff tools are free to use, with no signup required.',
  },
  {
    q: 'Do I need to sign up or log in?',
    a: 'No. You can use JSON AI Studio anonymously without an account. Logging in is optional and only adds per-user history and quota.',
  },
  {
    q: 'Can I save and organize my JSON in workspaces?',
    a: 'Yes. Log in to save your JSON into named workspaces as tagged documents, each keeping a full version history. Your work auto-saves, so you can switch between documents and resume anytime. Anonymous use stays local to your browser.',
  },
  {
    q: 'What can the AI do with my JSON?',
    a: 'The AI can explain unfamiliar or deeply nested JSON, edit it from natural-language instructions while keeping it valid, and produce a reviewable diff of every change.',
  },
  {
    q: 'Does it keep my JSON valid?',
    a: 'Yes. JSON AI Studio validates syntax after every AI edit, so you never download broken JSON.',
  },
  {
    q: 'Is JSON AI Studio open source?',
    a: 'Yes. The full source code is available on GitHub at github.com/rohity60/json-ai-studio.',
  },
  {
    q: 'Can it handle large JSON files?',
    a: 'Yes. It is built to open and work with large API payloads and configuration files that are hard to edit manually.',
  },
];

const faqJsonLd = {
  '@context': 'https://schema.org',
  '@type': 'FAQPage',
  mainEntity: faqs.map((f) => ({
    '@type': 'Question',
    name: f.q,
    acceptedAnswer: { '@type': 'Answer', text: f.a },
  })),
};

function StarPill({ stars }: { stars: number | null }) {
  return (
    <a
      href={REPO_URL}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-[#2c3e50] transition-colors hover:border-gray-400 hover:bg-gray-50"
    >
      <Github className="h-4 w-4" />
      <span className="hidden sm:inline">Star on GitHub</span>
      <span className="sm:hidden">GitHub</span>
      {stars !== null && (
        <span className="inline-flex items-center gap-1 rounded-md bg-gray-100 px-1.5 py-0.5 text-xs text-gray-600">
          <Star className="h-3 w-3 fill-amber-400 text-amber-400" />
          {stars.toLocaleString()}
        </span>
      )}
    </a>
  );
}

function Cell({ v }: { v: boolean | 'partial' }) {
  if (v === true) return <Check className="mx-auto h-5 w-5 text-emerald-600" aria-label="Yes" />;
  if (v === 'partial') return <Minus className="mx-auto h-5 w-5 text-amber-500" aria-label="Limited" />;
  return <X className="mx-auto h-5 w-5 text-gray-300" aria-label="No" />;
}

function Shot({ src, alt }: { src: string; alt: string }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={alt}
      className="w-full rounded-xl border border-gray-200 shadow-lg ring-1 ring-black/5"
      loading="lazy"
    />
  );
}

export default async function LandingV2() {
  const stars = await getStars();

  return (
    <div className="min-h-screen bg-white text-[#2c3e50]">
      <JsonLd data={faqJsonLd} />
      {/* Header */}
      <header className="sticky top-0 z-50 flex items-center justify-between border-b border-gray-200 bg-white/80 px-4 py-3 backdrop-blur">
        <Logo />
        <nav className="hidden items-center gap-1 text-sm md:flex">
          <Link href="/studio" className="rounded-lg px-3 py-1.5 text-gray-600 hover:bg-gray-100 hover:text-gray-900">Workspace</Link>
          <Link href="/templates" className="rounded-lg px-3 py-1.5 text-gray-600 hover:bg-gray-100 hover:text-gray-900">Templates</Link>
          <Link href="/blog" className="rounded-lg px-3 py-1.5 text-gray-600 hover:bg-gray-100 hover:text-gray-900">Blog</Link>
        </nav>
        <div className="flex items-center gap-2 sm:gap-3">
          <StarPill stars={stars} />
          <Link
            href="/studio"
            className="rounded-lg bg-purple-600 px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-purple-700"
          >
            Start Free
          </Link>
        </div>
      </header>

      <main>
        {/* Hero */}
        <section className="mx-auto max-w-6xl px-4 pt-20 pb-12 text-center md:pt-28">
          <div className="animate-fade-up mx-auto max-w-3xl">
            <span className="inline-flex items-center gap-2 rounded-full border border-purple-200 bg-purple-50 px-3 py-1 text-xs font-medium text-purple-700">
              <span className="h-1.5 w-1.5 rounded-full bg-purple-500" />
              The AI workspace for JSON
            </span>
            <h1 className="mt-6 text-4xl font-bold tracking-tight md:text-6xl">
              AI JSON Formatter <span className="text-purple-600">&amp; Editor</span>
            </h1>
            <p className="mx-auto mt-6 max-w-2xl text-lg text-gray-600">
              Format, explain, edit, validate and transform JSON using AI.
            </p>
            <p className="mx-auto mt-3 max-w-2xl text-base text-gray-500">
              Upload any JSON, describe changes in plain English, review every modification with
              side-by-side diffs and download valid JSON with confidence.
            </p>

            <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Link
                href="/studio"
                className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-8 py-3 text-base font-medium text-white transition-colors hover:bg-purple-700"
              >
                Start Free
                <ArrowRight className="h-4 w-4" />
              </Link>
              <a
                href={REPO_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-lg border border-gray-300 bg-white px-8 py-3 text-base font-medium text-[#2c3e50] transition-colors hover:border-gray-400 hover:bg-gray-50"
              >
                <Github className="h-4 w-4" />
                View on GitHub
              </a>
            </div>

            <div className="mt-6 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm text-gray-500">
              <span className="inline-flex items-center gap-1.5">
                <Check className="h-4 w-4 text-emerald-600" /> No signup required
              </span>
              <span className="inline-flex items-center gap-1.5">
                <Check className="h-4 w-4 text-emerald-600" /> Open Source
              </span>
              <span className="inline-flex items-center gap-1.5">
                <Check className="h-4 w-4 text-emerald-600" /> AI Powered
              </span>
            </div>
          </div>

          {/* Hero screenshot */}
          <div className="mx-auto mt-14 max-w-5xl">
            <Shot src="/landing/hero.png" alt="JSON AI Studio — AI chat, JSON tree and diff workspace" />
          </div>
        </section>

        {/* More than a formatter */}
        <section className="border-t border-gray-100 bg-gray-50/60 px-4 py-20">
          <div className="mx-auto max-w-3xl text-center">
            <h2 className="text-3xl font-bold tracking-tight md:text-4xl">
              More than an AI JSON Formatter
            </h2>
            <p className="mt-6 text-lg text-gray-600">
              JSON AI Studio isn&apos;t just another formatter.
            </p>
            <p className="mt-3 text-lg text-gray-600">
              It&apos;s a complete AI-powered workspace built specifically for developers working
              with JSON every day.
            </p>
          </div>
        </section>

        {/* Feature cards */}
        <section className="px-4 py-20">
          <div className="mx-auto max-w-6xl">
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              {features.map((f) => (
                <div
                  key={f.title}
                  className="rounded-xl border border-gray-200 bg-white p-6 transition duration-200 hover:-translate-y-0.5 hover:border-purple-200 hover:shadow-md"
                >
                  <div className="text-3xl">{f.emoji}</div>
                  <h3 className="mt-4 text-lg font-semibold">{f.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-gray-600">{f.copy}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Showcase rows with real screenshots */}
        <section className="border-t border-gray-100 bg-gray-50/60 px-4 py-20">
          <div className="mx-auto flex max-w-6xl flex-col gap-24">
            {/* Explain */}
            <div className="grid items-center gap-10 md:grid-cols-2">
              <div>
                <div className="text-3xl">🧠</div>
                <h3 className="mt-4 text-2xl font-bold tracking-tight">Explain any JSON in seconds</h3>
                <p className="mt-3 text-gray-600">
                  Point the AI JSON viewer at a deeply nested payload and get a plain-English
                  explanation of the structure, fields and intent — no more scrolling through
                  thousands of lines.
                </p>
              </div>
              <Shot src="/landing/explain.png" alt="AI explanation of a JSON structure" />
            </div>

            {/* Diff / Review */}
            <div className="grid items-center gap-10 md:grid-cols-2">
              <div className="md:order-2">
                <div className="text-3xl">🔍</div>
                <h3 className="mt-4 text-2xl font-bold tracking-tight">Review every change as a JSON diff</h3>
                <p className="mt-3 text-gray-600">
                  Every AI edit is a visual, side-by-side JSON diff. Compare before and after,
                  then accept only the changes you want — nothing is applied behind your back.
                </p>
              </div>
              <div className="md:order-1">
                <Shot src="/landing/diff.png" alt="Side-by-side JSON diff viewer" />
              </div>
            </div>

            {/* Workspaces */}
            <div className="grid items-center gap-10 md:grid-cols-2">
              <div>
                <div className="text-3xl">🗂️</div>
                <h3 className="mt-4 text-2xl font-bold tracking-tight">Organize everything in Workspaces</h3>
                <p className="mt-3 text-gray-600">
                  Save your JSON into named workspaces as tagged documents, each with its own version
                  history. Log in and your work auto-saves — switch between documents and pick up
                  exactly where you left off.
                </p>
              </div>
              <Shot
                src="/landing/workspaces.png"
                alt="JSON AI Studio workspace with saved documents and version history"
              />
            </div>
          </div>
        </section>

        {/* How it works */}
        <section className="px-4 py-20">
          <div className="mx-auto max-w-6xl">
            <div className="text-center">
              <h2 className="text-3xl font-bold tracking-tight md:text-4xl">How it Works</h2>
              <p className="mt-4 text-gray-600">From raw JSON to valid, reviewed output in five steps.</p>
            </div>

            <ol className="mt-14 grid gap-4 md:grid-cols-5">
              {workflow.map((step, i) => (
                <li key={step.title} className="relative">
                  <div className="flex h-full flex-col rounded-xl border border-gray-200 bg-white p-5">
                    <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-purple-100 text-sm font-semibold text-purple-700">
                      {i + 1}
                    </span>
                    <h3 className="mt-4 font-semibold">{step.title}</h3>
                    <p className="mt-1 text-sm text-gray-600">{step.copy}</p>
                  </div>
                  {i < workflow.length - 1 && (
                    <ArrowRight className="absolute -right-3 top-1/2 hidden h-5 w-5 -translate-y-1/2 text-gray-300 md:block" />
                  )}
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* Use cases */}
        <section className="border-t border-gray-100 bg-gray-50/60 px-4 py-20">
          <div className="mx-auto max-w-6xl">
            <div className="text-center">
              <h2 className="text-3xl font-bold tracking-tight md:text-4xl">Popular Use Cases</h2>
              <p className="mt-4 text-gray-600">
                What developers use the AI JSON editor and validator for every day.
              </p>
            </div>
            <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {useCases.map((uc) => (
                <div
                  key={uc}
                  className="rounded-xl border border-gray-200 bg-white p-5 text-sm font-medium transition-colors hover:border-purple-200"
                >
                  {uc}
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Comparison */}
        <section className="px-4 py-20">
          <div className="mx-auto max-w-5xl">
            <div className="text-center">
              <h2 className="text-3xl font-bold tracking-tight md:text-4xl">
                Why JSON AI Studio
              </h2>
              <p className="mt-4 text-gray-600">
                How it compares to traditional JSON editors and general AI chatbots.
              </p>
            </div>

            <div className="mt-12 overflow-x-auto">
              <table className="w-full min-w-[640px] border-collapse text-sm">
                <thead>
                  <tr className="border-b border-gray-200">
                    <th className="py-4 pr-4 text-left font-medium text-gray-500"></th>
                    <th className="rounded-t-lg bg-purple-50 px-4 py-4 text-center font-semibold text-purple-700">
                      JSON AI Studio
                    </th>
                    <th className="px-4 py-4 text-center font-medium text-gray-500">
                      Traditional JSON Editors
                    </th>
                    <th className="px-4 py-4 text-center font-medium text-gray-500">
                      General AI Chatbots
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {comparison.map(([label, a, b, c], i) => (
                    <tr key={label} className={i % 2 ? 'bg-gray-50/50' : ''}>
                      <td className="py-3 pr-4 font-medium">{label}</td>
                      <td className="bg-purple-50/50 px-4 py-3">
                        <Cell v={a} />
                      </td>
                      <td className="px-4 py-3">
                        <Cell v={b} />
                      </td>
                      <td className="px-4 py-3">
                        <Cell v={c} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        {/* Open source */}
        <section className="border-t border-gray-100 bg-gray-50/60 px-4 py-20">
          <div className="mx-auto max-w-3xl text-center">
            <div className="inline-flex items-center justify-center rounded-full bg-purple-100 p-3">
              <Github className="h-6 w-6 text-purple-700" />
            </div>
            <h2 className="mt-6 text-3xl font-bold tracking-tight md:text-4xl">
              Built in the Open. Built for Developers.
            </h2>
            <p className="mt-6 text-lg text-gray-600">JSON AI Studio is fully open source.</p>
            <p className="mt-3 text-gray-600">
              Developers can inspect the code, contribute features, report issues and help shape
              the future of the project.
            </p>
            <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <a
                href={REPO_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-lg bg-[#2c3e50] px-8 py-3 text-base font-medium text-white transition-colors hover:bg-[#1f2d3a]"
              >
                <Github className="h-5 w-5" />
                View on GitHub
                {stars !== null && (
                  <span className="inline-flex items-center gap-1 rounded-md bg-white/15 px-2 py-0.5 text-sm">
                    <Star className="h-3.5 w-3.5 fill-amber-400 text-amber-400" />
                    {stars.toLocaleString()}
                  </span>
                )}
              </a>
            </div>
          </div>
        </section>

        {/* FAQ */}
        <section id="faq" className="px-4 py-20">
          <div className="mx-auto max-w-3xl">
            <div className="text-center">
              <h2 className="text-3xl font-bold tracking-tight md:text-4xl">
                Frequently Asked Questions
              </h2>
              <p className="mt-4 text-gray-600">
                Everything you need to know about the AI JSON workspace.
              </p>
            </div>
            <div className="mt-12 space-y-4">
              {faqs.map((f) => (
                <details
                  key={f.q}
                  className="group rounded-xl border border-gray-200 bg-white p-5"
                >
                  <summary className="flex cursor-pointer list-none items-center justify-between font-semibold">
                    {f.q}
                    <ChevronDown className="h-5 w-5 shrink-0 text-gray-400 transition-transform group-open:rotate-180" />
                  </summary>
                  <p className="mt-3 text-sm leading-relaxed text-gray-600">{f.a}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        {/* Bottom CTA */}
        <section className="px-4 py-24 text-center">
          <div className="mx-auto max-w-2xl">
            <h2 className="text-3xl font-bold tracking-tight md:text-4xl">
              The smartest place to work with JSON
            </h2>
            <p className="mt-4 text-gray-600">
              Format, explain, edit and validate JSON with AI — free, no signup required.
            </p>
            <div className="mt-8">
              <Link
                href="/studio"
                className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-8 py-3 text-base font-medium text-white transition-colors hover:bg-purple-700"
              >
                Start Free
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-200 px-4 py-10">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-4 md:flex-row">
          <Logo />
          <p className="text-center text-sm text-gray-500 md:text-right">
            JSON AI Studio — the AI JSON formatter, editor, viewer, validator and diff tool. © 2026
          </p>
          <a
            href={REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-sm text-gray-500 transition-colors hover:text-[#2c3e50]"
          >
            <Github className="h-4 w-4" />
            GitHub
          </a>
        </div>
      </footer>
    </div>
  );
}
