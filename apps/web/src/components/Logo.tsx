import { FileJson2 } from 'lucide-react';

export default function Logo() {
  return (
    <div className="flex items-center gap-2">
      <FileJson2 className="w-6 h-6 text-purple-600" />
      <div className="logo-container opt-1">
        <span className="brand-main">JSON</span>
        <span className="brand-sub-1">AI</span>
        <span className="brand-sub-1">STUDIO</span>
      </div>
    </div>
  );
}
