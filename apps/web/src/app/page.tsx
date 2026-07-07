import Link from 'next/link';
import {
  Sparkles,
  UploadCloud,
  GitCompare,
  History,
  Layers,
  BookOpen,
  ArrowRight,
} from 'lucide-react';
import Logo from '@/components/Logo';

const features = [
  {
    icon: Sparkles,
    title: 'AI formatting & editing',
    copy: 'Ask in plain English — the AI formats and modifies your JSON without ever breaking it.',
  },
  {
    icon: UploadCloud,
    title: 'Upload any JSON',
    copy: 'Drop in a file or paste raw JSON and start editing in seconds.',
  },
  {
    icon: GitCompare,
    title: 'Side-by-side diffs',
    copy: 'Compare every AI change against the original before you accept it.',
  },
  {
    icon: History,
    title: 'Version history',
    copy: 'Save versions of your JSON and restore any of them at any time.',
  },
  {
    icon: Layers,
    title: 'Multiple sessions',
    copy: 'Work on several JSON documents at the same time.',
  },
  {
    icon: BookOpen,
    title: 'AI explanations',
    copy: 'Get a plain-English explanation of any JSON structure with one click.',
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen flex flex-col bg-white">
      {/* Header */}
      <header className="border-b bg-white px-4 py-3 flex items-center justify-between">
        <Logo />
        <Link
          href="/studio"
          className="px-4 py-1.5 bg-purple-600 text-white text-sm rounded-lg hover:bg-purple-700"
        >
          Open Studio
        </Link>
      </header>

      <main className="flex-1">
        {/* Hero */}
        <section className="max-w-4xl mx-auto text-center px-4 py-20 md:py-28">
          <h1 className="text-4xl md:text-5xl font-bold text-[#2c3e50]">
            Format JSON Online <span className="text-purple-600">with AI</span>
          </h1>
          <p className="mt-6 text-lg text-gray-600 max-w-2xl mx-auto">
            JSON AI Studio is a free online AI JSON formatter and editor. Upload your JSON, tell
            the AI what to change, and get valid, perfectly formatted JSON every time — no manual
            formatting, no broken files.
          </p>
          <div className="mt-8">
            <Link
              href="/studio"
              className="px-8 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 text-base font-medium inline-flex items-center gap-2"
            >
              Start Formatting — Free
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
          <p className="mt-4 text-sm text-gray-400">No sign-up required.</p>
        </section>

        {/* Feature grid */}
        <section className="bg-gray-50 border-t px-4 py-16">
          <h2 className="text-2xl md:text-3xl font-bold text-center text-[#2c3e50]">
            Everything you need to work with JSON
          </h2>
          <div className="mt-10 grid md:grid-cols-3 gap-6 max-w-5xl mx-auto">
            {features.map(({ icon: Icon, title, copy }) => (
              <div key={title} className="bg-white rounded-lg border p-6">
                <Icon className="w-6 h-6 text-purple-600" />
                <h3 className="mt-3 font-semibold text-[#2c3e50]">{title}</h3>
                <p className="mt-2 text-sm text-gray-600">{copy}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Bottom CTA */}
        <section className="border-t px-4 py-16 text-center">
          <h2 className="text-2xl font-bold text-[#2c3e50]">Ready to format your JSON?</h2>
          <div className="mt-6">
            <Link
              href="/studio"
              className="px-8 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 text-base font-medium inline-flex items-center gap-2"
            >
              Open Studio
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t px-4 py-6">
        <div className="max-w-5xl mx-auto flex flex-col md:flex-row items-center justify-between gap-2 text-sm text-gray-500">
          <Logo />
          <p>JSON AI Studio — free online AI JSON formatter, editor, and diff tool. © 2026</p>
        </div>
      </footer>
    </div>
  );
}
