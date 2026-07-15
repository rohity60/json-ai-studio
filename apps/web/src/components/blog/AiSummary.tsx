import { Sparkles } from 'lucide-react';

export default function AiSummary({ text }: { text: string }) {
  if (!text) return null;
  return (
    <div className="my-6 rounded-xl border border-purple-100 bg-purple-50/60 p-4">
      <div className="mb-1 flex items-center gap-1.5 text-sm font-semibold text-purple-700">
        <Sparkles className="h-4 w-4" />
        AI Summary
      </div>
      <p className="text-sm leading-relaxed text-gray-700">{text}</p>
    </div>
  );
}
