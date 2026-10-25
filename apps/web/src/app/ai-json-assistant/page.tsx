import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight, Check } from 'lucide-react';
import SiteHeader from '@/components/site/SiteHeader';
import JsonLd from '@/components/JsonLd';

// Landing page for the "AI assistant for JSON" search intent. The homepage
// targets "AI JSON formatter/editor"; this page owns the assistant phrasing.
// Only describe features that are live on release.

const URL = 'https://jsonaistudio.com/ai-json-assistant';

export const metadata: Metadata = {
  // absolute: skip the site-wide " — JSON AI Studio" suffix (~60-char SERP cut).
  title: { absolute: 'AI Assistant for JSON — Edit JSON in Plain English' },
  description:
    'An AI assistant for JSON: describe a change in plain English, review every edit as a side-by-side diff, accept or reject each one, and download valid JSON. Free, no signup.',
  keywords: [
    'ai assistant for json',
    'json ai assistant',
    'ai json assistant',
    'edit json with ai',
    'json ai',
    'ai json editor',
    'fix json with ai',
  ],
  alternates: { canonical: URL },
  openGraph: {
    title: 'AI Assistant for JSON — JSON AI Studio',
    description:
      'Edit, fix and explain JSON in plain English. Every AI change is a reviewable diff.',
    url: URL,
    type: 'website',
  },
};

const EXAMPLES: { prompt: string; result: string }[] = [
  {
    prompt: 'Move zod to devDependencies',
    result: 'Two diffs: delete dependencies.zod, add devDependencies.zod — same version, nothing else touched.',
  },
  {
    prompt: 'Set retryCount to 3 for the payments service',
    result: 'One precise change at services.payments.retryCount, shown as a before/after diff.',
  },
  {
    prompt: 'Do the same for all such services',
    result: 'The assistant remembers the previous change and applies it to every matching service.',
  },
  {
    prompt: 'I want every modifiedDate to match its creationDate',
    result: 'Each entry gets its own creationDate copied — across hundreds of records in one request.',
  },
  {
    prompt: 'Is this Zoom Rooms profile valid? Fix what is wrong',
    result: 'Invalid values are corrected, and the explanation says why each fix was made.',
  },
];

const FAQ: { q: string; a: string }[] = [
  {
    q: 'What is an AI assistant for JSON?',
    a: 'A tool you talk to in plain English instead of hand-editing JSON. You describe the change ("rename the service", "remove all null values", "copy creationDate into modifiedDate") and the assistant proposes the exact edits. In JSON AI Studio every proposal is a field-level diff you can accept or reject before anything is saved.',
  },
  {
    q: 'How is this different from pasting JSON into a chatbot?',
    a: 'A chatbot rewrites the whole document and you have to trust it. JSON AI Studio applies changes as individual diffs against your actual file, validates them, never touches fields you did not ask about, and lets you reject any single change. You always download valid JSON.',
  },
  {
    q: 'Does it work with large JSON files?',
    a: 'Yes. For large documents the assistant works from the document’s key structure plus statistics computed over every element, and changes that hit many elements (for example "the first 100 records") are applied server-side against the complete file, so nothing is guessed.',
  },
  {
    q: 'Does the assistant remember earlier messages?',
    a: 'Yes. Follow-ups like "do the same for the rest" or "undo that" use the conversation history, including which changes you accepted or rejected.',
  },
  {
    q: 'Is it free?',
    a: 'Yes. You can use it without signing up. Logging in gives you your own quota and saved workspaces. The project is open source.',
  },
];

const faqJsonLd = {
  '@context': 'https://schema.org',
  '@type': 'FAQPage',
  mainEntity: FAQ.map((f) => ({
    '@type': 'Question',
    name: f.q,
    acceptedAnswer: { '@type': 'Answer', text: f.a },
  })),
};

const breadcrumbJsonLd = {
  '@context': 'https://schema.org',
  '@type': 'BreadcrumbList',
  itemListElement: [
    { '@type': 'ListItem', position: 1, name: 'Home', item: 'https://jsonaistudio.com' },
    { '@type': 'ListItem', position: 2, name: 'AI Assistant for JSON', item: URL },
  ],
};

export default function AiJsonAssistantPage() {
  return (
    <div className="min-h-screen bg-white text-gray-900">
      <JsonLd data={faqJsonLd} />
      <JsonLd data={breadcrumbJsonLd} />
      <SiteHeader />

      <main className="mx-auto max-w-4xl px-4 py-16">
        <section className="text-center">
          <h1 className="text-4xl font-bold tracking-tight md:text-5xl">AI Assistant for JSON</h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-gray-600">
            JSON AI Studio is an AI assistant for JSON: tell it what to change in plain English
            and it edits your file for you — one reviewable diff at a time. Accept the changes you
            want, reject the rest, and download valid JSON.
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link
              href="/studio?tab=upload"
              data-gtag-conversion
              className="inline-flex items-center gap-2 rounded-lg bg-purple-600 px-8 py-3 font-medium text-white hover:bg-purple-700"
            >
              Open the assistant with your JSON <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/studio?sample=package"
              data-gtag-conversion
              className="inline-flex items-center gap-2 rounded-lg border border-purple-300 px-8 py-3 font-medium text-purple-700 hover:bg-purple-50"
            >
              Try it on a sample
            </Link>
          </div>
          <p className="mt-4 text-sm text-gray-500">Free · No signup · Open source</p>
        </section>

        <section className="mt-20">
          <h2 className="text-2xl font-bold tracking-tight md:text-3xl">
            What the JSON assistant does
          </h2>
          <ul className="mt-6 space-y-4 text-gray-700">
            {[
              ['Edits JSON from plain English', 'Describe the change; the assistant finds the exact fields and proposes add, modify or delete diffs — never a blind rewrite of your file.'],
              ['Shows every change before it lands', 'Side-by-side before/after view and a change list. Accept or reject each diff individually, or all at once.'],
              ['Remembers the conversation', '“Do the same for the others”, “undo that”, “only the ones in chapter 1” — follow-ups use earlier turns and what you accepted or rejected.'],
              ['Handles bulk changes', 'One request can update hundreds of matching elements; the server applies it against the full document and reports how many locations matched.'],
              ['Fixes format mistakes', 'For known formats it flags and corrects invalid values — and explains why — while applying exactly what you ask for when you insist.'],
              ['Explains unfamiliar JSON', 'One click summarizes what a document is, its main objects, important fields and potential issues.'],
            ].map(([title, body]) => (
              <li key={title} className="flex gap-3">
                <Check className="mt-1 h-5 w-5 flex-shrink-0 text-emerald-600" />
                <span>
                  <strong className="font-semibold text-gray-900">{title}.</strong> {body}
                </span>
              </li>
            ))}
          </ul>
        </section>

        <section className="mt-20">
          <h2 className="text-2xl font-bold tracking-tight md:text-3xl">Things you can ask it</h2>
          <div className="mt-6 overflow-hidden rounded-xl border border-gray-200">
            {EXAMPLES.map((e, i) => (
              <div key={e.prompt} className={`p-4 ${i ? 'border-t border-gray-200' : ''}`}>
                <p className="font-mono text-sm text-purple-700">“{e.prompt}”</p>
                <p className="mt-1 text-sm text-gray-600">{e.result}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-20">
          <h2 className="text-2xl font-bold tracking-tight md:text-3xl">
            AI assistant vs. JSON formatters and chatbots
          </h2>
          <div className="mt-6 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-gray-200 text-gray-500">
                <tr>
                  <th className="py-2 pr-4 font-medium"></th>
                  <th className="py-2 pr-4 font-medium">JSON formatter</th>
                  <th className="py-2 pr-4 font-medium">General chatbot</th>
                  <th className="py-2 font-medium text-purple-700">JSON AI Studio</th>
                </tr>
              </thead>
              <tbody className="text-gray-700">
                {[
                  ['Edit with plain English', 'No', 'Yes', 'Yes'],
                  ['Changes shown as diffs', 'No', 'No', 'Yes, field by field'],
                  ['Accept / reject each change', 'No', 'No', 'Yes'],
                  ['Guaranteed valid JSON output', 'Yes', 'No', 'Yes'],
                  ['Remembers follow-ups', 'No', 'Yes', 'Yes, with change status'],
                  ['Large files', 'Yes', 'Often truncates', 'Yes, server-side bulk edits'],
                ].map(([row, ...cells]) => (
                  <tr key={row} className="border-b border-gray-100">
                    <td className="py-2 pr-4 font-medium text-gray-900">{row}</td>
                    {cells.map((c, i) => (
                      <td key={i} className={`py-2 pr-4 ${i === 2 ? 'text-purple-700' : ''}`}>
                        {c}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="mt-20">
          <h2 className="text-2xl font-bold tracking-tight md:text-3xl">How to use it</h2>
          <ol className="mt-6 list-decimal space-y-2 pl-5 text-gray-700">
            <li>
              Open the <Link href="/studio?tab=upload" className="text-purple-700 underline">workspace</Link> and
              upload or paste your JSON — or start from a{' '}
              <Link href="/templates" className="text-purple-700 underline">template</Link>.
            </li>
            <li>Type what you want changed in the chat, in plain English.</li>
            <li>Review the proposed diffs; accept or reject each one.</li>
            <li>Download the result, save it as a version, or keep refining.</li>
          </ol>
        </section>

        <section className="mt-20">
          <h2 className="text-2xl font-bold tracking-tight md:text-3xl">FAQ</h2>
          <div className="mt-6 space-y-6">
            {FAQ.map((f) => (
              <div key={f.q}>
                <h3 className="font-semibold text-gray-900">{f.q}</h3>
                <p className="mt-2 text-gray-600">{f.a}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-20 rounded-2xl bg-purple-50 p-8 text-center">
          <h2 className="text-2xl font-bold tracking-tight">Try the AI assistant for JSON</h2>
          <p className="mt-3 text-gray-600">Upload a file and describe your first change.</p>
          <Link
            href="/studio?tab=upload"
            data-gtag-conversion
            className="mt-6 inline-flex items-center gap-2 rounded-lg bg-purple-600 px-8 py-3 font-medium text-white hover:bg-purple-700"
          >
            Open JSON AI Studio <ArrowRight className="h-4 w-4" />
          </Link>
        </section>
      </main>
    </div>
  );
}
