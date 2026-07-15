'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';
import CopyButton from './CopyButton';

/** Renders a blog markdown body. The project has no @tailwindcss/typography
 *  plugin, so every element is styled explicitly via the components map.
 *  Fenced code blocks get a copy button. */
const components: Components = {
  h1: (p) => <h1 className="mt-8 mb-3 text-2xl font-bold text-gray-900" {...p} />,
  h2: (p) => <h2 className="mt-8 mb-3 text-xl font-bold text-gray-900" {...p} />,
  h3: (p) => <h3 className="mt-6 mb-2 text-lg font-semibold text-gray-900" {...p} />,
  p: (p) => <p className="my-4 leading-relaxed text-gray-700" {...p} />,
  ul: (p) => <ul className="my-4 list-disc space-y-1 pl-6 text-gray-700" {...p} />,
  ol: (p) => <ol className="my-4 list-decimal space-y-1 pl-6 text-gray-700" {...p} />,
  a: (p) => <a className="text-purple-600 hover:underline" {...p} />,
  blockquote: (p) => (
    <blockquote className="my-4 border-l-4 border-purple-200 pl-4 text-gray-600 italic" {...p} />
  ),
  strong: (p) => <strong className="font-semibold text-gray-900" {...p} />,
  table: (p) => (
    <div className="my-4 overflow-x-auto">
      <table className="w-full border-collapse text-sm" {...p} />
    </div>
  ),
  thead: (p) => <thead className="bg-gray-50" {...p} />,
  th: (p) => (
    <th className="border border-gray-200 px-3 py-2 text-left font-semibold text-gray-900" {...p} />
  ),
  td: (p) => <td className="border border-gray-200 px-3 py-2 align-top text-gray-700" {...p} />,
  code(props) {
    const { children, className } = props as any;
    const isBlock = /language-/.test(className || '');
    if (!isBlock) {
      return (
        <code className="rounded bg-gray-100 px-1.5 py-0.5 text-sm text-purple-700">
          {children}
        </code>
      );
    }
    const text = String(children).replace(/\n$/, '');
    return (
      <span className="relative my-4 block">
        <CopyButton text={text} />
        <code className="block overflow-x-auto rounded-xl bg-gray-950 p-4 text-xs leading-relaxed text-gray-100">
          {text}
        </code>
      </span>
    );
  },
  pre: (p) => <>{p.children}</>,
};

export default function PostBody({ body }: { body: string }) {
  return (
    <div className="text-[15px]">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {body}
      </ReactMarkdown>
    </div>
  );
}
