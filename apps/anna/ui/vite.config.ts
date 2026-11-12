import path from 'node:path';
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';

const here = path.dirname(fileURLToPath(import.meta.url));
const webSrc = path.resolve(here, '../../web/src');
const annaApi = path.resolve(here, 'src/anna/api.ts');
const webApi = path.resolve(webSrc, 'lib/api');

/** The web app's session code imports its HTTP client as `../lib/api` or
 *  `@/lib/api`. In this build every such import resolves to the Anna
 *  adapter instead, so that code runs unchanged over the Executa. */
function swapApiClient(): Plugin {
  return {
    name: 'jas-swap-api-client',
    enforce: 'pre',
    resolveId(source, importer) {
      if (source === '@/lib/api') return annaApi;
      if (importer && source.startsWith('.')) {
        const resolved = path.resolve(path.dirname(importer), source);
        if (resolved === webApi) return annaApi;
      }
      return null;
    },
  };
}

export default defineConfig({
  // The host mounts the bundle under /anna-apps/<slug>/…: keep URLs relative.
  base: './',
  plugins: [swapApiClient(), react()],
  resolve: {
    alias: [
      { find: '@/lib/openInWorkspace', replacement: path.resolve(here, 'src/shims/openInWorkspace.ts') },
      { find: /^@\//, replacement: `${webSrc}/` },
    ],
    // Files under apps/web/src must use this package's copies, not a second
    // React (or toaster) from apps/web/node_modules.
    dedupe: [
      'react', 'react-dom', 'sonner', 'lucide-react', 'idb', 'deep-diff',
      'react-diff-viewer', 'react-json-view-lite', 'react-markdown', 'remark-gfm',
    ],
  },
  build: {
    outDir: path.resolve(here, '../bundle'),
    emptyOutDir: true,
    target: 'es2022',
  },
});
