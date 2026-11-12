/** @type {import('tailwindcss').Config} */
export default {
  // Classes come from this package and from the reused web components.
  content: [
    './index.html',
    './src/**/*.{ts,tsx}',
    '../../web/src/components/**/*.{ts,tsx}',
    '../../web/src/context/**/*.{ts,tsx}',
  ],
  theme: { extend: {} },
  plugins: [],
};
