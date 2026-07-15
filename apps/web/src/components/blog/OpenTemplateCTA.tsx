import OpenInWorkspaceButton from '@/components/templates/OpenInWorkspaceButton';
import JsonPreview from '@/components/templates/JsonPreview';
import { getTemplateBySlug } from '@/lib/templates';

/** In-article CTA (BL-02): shows a related template's JSON with an
 *  "Open in AI Workspace" action, so a blog post funnels into the studio. */
export default function OpenTemplateCTA({ slug }: { slug: string }) {
  const tpl = getTemplateBySlug(slug);
  if (!tpl) return null;
  const { meta, json } = tpl;
  return (
    <div className="my-6 rounded-xl border border-gray-200 bg-gray-50 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-semibold text-gray-900">{meta.title}</div>
          <div className="text-xs text-gray-500">{meta.description}</div>
        </div>
        <OpenInWorkspaceButton meta={meta} json={json} label="Try in Workspace" />
      </div>
      <JsonPreview json={json} />
    </div>
  );
}
