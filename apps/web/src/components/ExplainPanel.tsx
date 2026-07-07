'use client';

import React from 'react';
import ReactMarkdown from 'react-markdown';
import { RotateCcw, Sparkles } from 'lucide-react';

interface ExplainPanelProps {
    markdown: string;
    onRetry?: () => void;
    loading?: boolean;
    error?: string | null;
}

// Explicit element styles -- the project has no @tailwindcss/typography plugin,
// so `prose` classes are no-ops and ReactMarkdown output renders unstyled.
const mdComponents = {
    h1: ({ ...props }: any) => (
        <h2 className="text-base font-bold text-gray-900 mt-4 mb-2 pb-1 border-b border-purple-200 first:mt-0" {...props} />
    ),
    h2: ({ ...props }: any) => (
        <h3 className="text-sm font-bold text-purple-800 uppercase tracking-wide mt-4 mb-1.5 first:mt-0" {...props} />
    ),
    h3: ({ ...props }: any) => (
        <h4 className="text-sm font-semibold text-gray-900 mt-3 mb-1" {...props} />
    ),
    p: ({ ...props }: any) => (
        <p className="text-sm text-gray-700 leading-relaxed mb-2" {...props} />
    ),
    strong: ({ ...props }: any) => (
        <strong className="font-semibold text-gray-900 bg-amber-100/80 px-1 rounded" {...props} />
    ),
    em: ({ ...props }: any) => <em className="italic text-gray-800" {...props} />,
    code: ({ ...props }: any) => (
        <code className="font-mono text-xs bg-purple-50 text-purple-700 border border-purple-100 px-1 py-0.5 rounded" {...props} />
    ),
    pre: ({ ...props }: any) => (
        <pre className="bg-gray-900 text-gray-100 text-xs rounded-lg p-3 overflow-x-auto mb-3 [&_code]:bg-transparent [&_code]:border-0 [&_code]:text-gray-100 [&_code]:p-0" {...props} />
    ),
    ul: ({ ...props }: any) => (
        <ul className="list-disc pl-5 mb-2 space-y-1 text-sm text-gray-700" {...props} />
    ),
    ol: ({ ...props }: any) => (
        <ol className="list-decimal pl-5 mb-2 space-y-1 text-sm text-gray-700" {...props} />
    ),
    li: ({ ...props }: any) => <li className="leading-relaxed" {...props} />,
    blockquote: ({ ...props }: any) => (
        <blockquote className="border-l-4 border-amber-400 bg-amber-50 text-sm text-gray-700 px-3 py-2 rounded-r mb-2" {...props} />
    ),
    table: ({ ...props }: any) => (
        <div className="overflow-x-auto mb-3">
            <table className="text-sm border-collapse w-full" {...props} />
        </div>
    ),
    th: ({ ...props }: any) => (
        <th className="text-left font-semibold text-purple-800 bg-purple-50 border border-purple-100 px-2 py-1" {...props} />
    ),
    td: ({ ...props }: any) => (
        <td className="border border-gray-200 px-2 py-1 text-gray-700" {...props} />
    ),
    hr: ({ ...props }: any) => <hr className="my-3 border-gray-200" {...props} />,
    a: ({ ...props }: any) => (
        <a className="text-purple-700 underline hover:text-purple-900" {...props} />
    ),
};

export default function ExplainPanel({
    markdown,
    onRetry,
    loading = false,
    error = null,
}: ExplainPanelProps) {
    return (
        <div className="mt-4 border border-purple-200 rounded-lg bg-white shadow-sm">
            <div className="flex items-center justify-between border-b border-purple-100 bg-purple-50/60 px-4 py-2 rounded-t-lg">
                <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-purple-600" />
                    <span className="text-sm font-medium text-purple-900">AI Explanation</span>
                </div>
                {onRetry && markdown && !loading && !error && (
                    <button
                        onClick={onRetry}
                        className="px-2 py-1 text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
                        title="Re-run explanation"
                    >
                        <RotateCcw className="w-3 h-3" />
                        Refresh
                    </button>
                )}
            </div>

            <div className="max-h-[45vh] overflow-y-auto p-4">
                {loading ? (
                    <div className="flex items-center justify-center py-8">
                        <div className="text-center">
                            <Sparkles className="w-8 h-8 mx-auto mb-2 text-purple-500 animate-pulse" />
                            <p className="text-sm text-muted-foreground">Explaining...</p>
                        </div>
                    </div>
                ) : error ? (
                    <div className="flex flex-col items-center justify-center py-6 gap-4">
                        <p className="text-sm text-red-500">{error}</p>
                        {onRetry && (
                            <button
                                onClick={onRetry}
                                className="px-4 py-2 text-sm bg-purple-600 text-white rounded-lg hover:bg-purple-700 flex items-center gap-2"
                            >
                                <RotateCcw className="w-4 h-4" />
                                Retry
                            </button>
                        )}
                    </div>
                ) : (
                    <ReactMarkdown components={mdComponents}>{markdown}</ReactMarkdown>
                )}
            </div>
        </div>
    );
}
