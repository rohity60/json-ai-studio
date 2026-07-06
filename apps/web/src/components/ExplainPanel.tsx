'use client';

import React from 'react';
import ReactMarkdown from 'react-markdown';
import { ArrowLeft, RotateCcw, Sparkles } from 'lucide-react';

interface ExplainPanelProps {
    markdown: string;
    onBack: () => void;
    onRetry?: () => void;
    loading?: boolean;
    error?: string | null;
}

export default function ExplainPanel({
    markdown,
    onBack,
    onRetry,
    loading = false,
    error = null,
}: ExplainPanelProps) {
    if (loading) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="text-center">
                    <Sparkles className="w-8 h-8 mx-auto mb-2 text-purple-500 animate-pulse" />
                    <p className="text-sm text-muted-foreground">Explaining...</p>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex flex-col items-center justify-center h-full gap-4">
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
        );
    }

    return (
        <div className="flex flex-col h-full">
            <div className="flex items-center justify-between border-b px-4 py-2">
                <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-purple-600" />
                    <span className="text-sm font-medium">AI Explanation</span>
                </div>
                <button
                    onClick={onBack}
                    className="px-3 py-1 text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
                >
                    <ArrowLeft className="w-3 h-3" />
                    Back
                </button>
            </div>
            <div className="flex-1 overflow-auto p-4 prose prose-sm max-w-none">
                <ReactMarkdown>{markdown}</ReactMarkdown>
            </div>
        </div>
    );
}
