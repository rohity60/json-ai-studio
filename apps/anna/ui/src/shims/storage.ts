// The shared session code reads localStorage directly. Inside a sandboxed
// app iframe that can throw; fall back to an in-memory store so the app
// still works for the length of the visit.
export function ensureLocalStorage(): void {
  try {
    const probe = '__jas_probe__';
    window.localStorage.setItem(probe, '1');
    window.localStorage.removeItem(probe);
    return;
  } catch {
    // fall through to the in-memory shim
  }
  const data = new Map<string, string>();
  const memory: Storage = {
    get length() { return data.size; },
    clear: () => data.clear(),
    getItem: (key) => (data.has(key) ? data.get(key)! : null),
    key: (index) => Array.from(data.keys())[index] ?? null,
    removeItem: (key) => { data.delete(key); },
    setItem: (key, value) => { data.set(key, String(value)); },
  };
  Object.defineProperty(window, 'localStorage', { value: memory, configurable: true });
}
