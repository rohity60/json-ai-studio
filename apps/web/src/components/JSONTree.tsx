'use client';

import { JsonView } from 'react-json-view-lite';
import 'react-json-view-lite/dist/index.css';

type JSONTreeProps = {
  data: Record<string, any>;
  name?: string;
  collapsible?: boolean;
};

export default function JSONTree({ data, name }: JSONTreeProps) {
  if (Object.keys(data).length === 0) {
    return (
       <div className="flex items-center justify-center h-32 text-sm text-muted-foreground">
         Empty JSON &mdash; upload or send a message to populate
       </div>
     );
   }

  return (
     <div className="overflow-auto max-h-[60vh] bg-gray-50 rounded-lg p-4 border border-gray-200">
       {name && (
         <div className="text-xs font-semibold text-muted-foreground mb-2 uppercase tracking-wide">{name}</div>
       )}
       <JsonView data={data} shouldExpandNode={(level) => level < 2} />
     </div>
   );
}
