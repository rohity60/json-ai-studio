/** Anonymous API key accessor for pages outside the SessionProvider
 *  (templates/blog). Mirrors the key SessionContext creates so a template
 *  opened from a marketing page shares the same anonymous credit identity.
 *  Client-only. */

const KEY = 'json-ai-studio-api-key';

export function getAnonApiKey(): string {
  if (typeof window === 'undefined') return '';
  let key = localStorage.getItem(KEY);
  if (!key) {
    key = crypto.randomUUID();
    localStorage.setItem(KEY, key);
  }
  return key;
}
