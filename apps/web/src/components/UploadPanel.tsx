'use client';

import { useState, useRef } from 'react';
import { FileJson2, Upload } from 'lucide-react';
import JSONTree from './JSONTree';

type UploadPanelProps = {
  onUpload: (json: Record<string, any>) => void;
};

export default function UploadPanel({ onUpload }: UploadPanelProps) {
  const [dragging, setDragging] = useState(false);
  const [pasteText, setPasteText] = useState('');
  const [parseError, setParseError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrop = async (e: React.DragEvent) => {
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (!file || !file.name.endsWith('.json')) return;
    const text = await file.text();
    try {
      onUpload(JSON.parse(text) as Record<string, any>);
    } catch {
      setParseError('Invalid JSON in file');
    }
  };

  const handlePasteSubmit = () => {
    try {
      setParseError(null);
      onUpload(JSON.parse(pasteText) as Record<string, any>);
    } catch (err: any) {
      setParseError(err.message);
    }
  };

  return (
    <div className="space-y-4">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
          dragging ? 'border-purple-500 bg-purple-50' : 'border-gray-300 hover:border-gray-400'
        }`}
      >
        <FileJson2 className="w-10 h-10 mx-auto text-muted-foreground mb-2" />
        <p className="text-sm font-medium">Drop a .json file here</p>
        <p className="text-xs text-muted-foreground mt-1">or click to browse</p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".json"
          className="hidden"
          onChange={async (e) => {
            const file = e.target.files?.[0];
            if (!file) return;
            try {
              onUpload(JSON.parse(await file.text()) as Record<string, any>);
            } catch (err: any) {
              setParseError(err.message);
              e.target.value = '';
            }
          }}
        />
      </div>

      <div className="border rounded-xl p-4 space-y-2">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Or paste JSON</p>
        <textarea
          value={pasteText}
          onChange={(e) => { setPasteText(e.target.value); setParseError(null); }}
          placeholder='{"key": "value"}'
          rows={4}
          className="w-full rounded-lg border px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
        />
        <button
          onClick={handlePasteSubmit}
          disabled={!pasteText.trim()}
          className="px-4 py-1.5 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 disabled:opacity-50 transition-colors"
        >
          Upload
        </button>
        {parseError && <p className="text-xs text-red-500">{parseError}</p>}
      </div>
    </div>
  );
}

