#!/usr/bin/env node
/** Export template format notes for the API chat prompt.
 *
 * Reads every content/templates/*.ts module (Node strips the TS types; the
 * modules only `import type`), keeps templates that declare a
 * `formatSignature`, and writes apps/api/src/json_ai_studio/config/
 * format_notes.json. Run after editing a template's signature or docs:
 *
 *   node --no-warnings apps/web/scripts/export-format-notes.mjs
 */

import { readdir, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const templatesDir = join(here, '..', 'src', 'content', 'templates');
const out = join(here, '..', '..', 'api', 'src', 'json_ai_studio', 'config', 'format_notes.json');

const files = (await readdir(templatesDir)).filter((f) => f.endsWith('.ts') && f !== 'index.ts').sort();
const formats = [];
for (const file of files) {
  const { template } = await import(pathToFileURL(join(templatesDir, file)).href);
  const meta = template?.meta;
  if (!meta?.formatSignature?.length) continue;
  formats.push({
    id: meta.id,
    title: meta.title,
    signature: meta.formatSignature,
    notes: [...meta.requiredFields, ...meta.optionalFields, ...meta.bestPractices],
  });
}

await writeFile(out, JSON.stringify({ generatedFrom: 'apps/web/src/content/templates', formats }, null, 2) + '\n');
console.log(`wrote ${formats.length} format(s) to ${out}`);
