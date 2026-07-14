import { ImageResponse } from 'next/og';

// Next file convention: this generates og:image (and, via twitter-image.tsx,
// twitter:image) for every route — no committed binary asset needed.
export const alt = 'JSON AI Studio — AI JSON Formatter & Editor';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          height: '100%',
          width: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'flex-start',
          justifyContent: 'center',
          backgroundColor: '#0f0a1e',
          backgroundImage: 'linear-gradient(135deg, #1e1235 0%, #0f0a1e 60%)',
          padding: '80px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
          <div
            style={{
              display: 'flex',
              height: 72,
              width: 72,
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: 18,
              backgroundColor: '#7c3aed',
              color: 'white',
              fontSize: 40,
              fontWeight: 700,
            }}
          >
            {'{ }'}
          </div>
          <div style={{ color: '#c4b5fd', fontSize: 30, fontWeight: 600 }}>JSON AI Studio</div>
        </div>
        <div
          style={{
            marginTop: 40,
            color: 'white',
            fontSize: 68,
            fontWeight: 800,
            lineHeight: 1.1,
            maxWidth: 900,
          }}
        >
          AI JSON Formatter &amp; Editor
        </div>
        <div style={{ marginTop: 28, color: '#a1a1aa', fontSize: 32, maxWidth: 940 }}>
          Format, explain, edit, validate and diff JSON with AI — free, no signup.
        </div>
      </div>
    ),
    { ...size },
  );
}
