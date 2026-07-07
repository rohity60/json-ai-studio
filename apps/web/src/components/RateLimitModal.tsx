'use client';

import { useState, useEffect } from 'react';
import { Clock } from 'lucide-react';

// Module-level store for modal state — callable from anywhere (context, api
// callbacks) without prop drilling. Same pattern as VersionModal.
export type RateLimitInfo = {
  message?: string;
  retryAfter?: number; // seconds until the caller may retry
  scope?: string; // "api" | "model"
};

let _info: RateLimitInfo | null = null;
let _listeners: Array<() => void> = [];

function _notify() {
  for (const listener of _listeners) listener();
}

/** Open the rate-limit popup. Safe to call from anywhere. */
export function showRateLimitModal(info: RateLimitInfo = {}) {
  _info = info;
  _notify();
}

export function hideRateLimitModal() {
  _info = null;
  _notify();
}

export default function RateLimitModal() {
  const [info, setInfo] = useState<RateLimitInfo | null>(null);
  const [remaining, setRemaining] = useState(0);

  // Subscribe to the module store. Sync immediately on mount too: a caller may
  // have opened the modal while it was unmounted (the provider unmounts the
  // whole tree during its `loading` flag), so read the pending value now.
  useEffect(() => {
    const handler = () => {
      setInfo(_info);
      if (_info) setRemaining(Math.max(0, Math.round(_info.retryAfter ?? 60)));
    };
    _listeners.push(handler);
    handler();
    return () => {
      _listeners = _listeners.filter((l) => l !== handler);
    };
  }, []);

  // Count down once the popup is open.
  useEffect(() => {
    if (!info || remaining <= 0) return;
    const t = setInterval(() => {
      setRemaining((r) => (r <= 1 ? 0 : r - 1));
    }, 1000);
    return () => clearInterval(t);
  }, [info, remaining]);

  if (!info) return null;

  const message =
    info.message ||
    "You've hit the rate limit. Please wait a moment before trying again.";

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'rgba(0, 0, 0, 0.25)',
      }}
      onClick={() => hideRateLimitModal()}
    >
      <div
        style={{
          backgroundColor: 'white',
          borderRadius: '0.75rem',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
          padding: '1.5rem',
          width: '100%',
          maxWidth: '22rem',
          marginLeft: '1rem',
          marginRight: '1rem',
          border: '1px solid #e5e7eb',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '2rem',
              height: '2rem',
              borderRadius: '9999px',
              backgroundColor: '#f3e8ff',
              color: '#7c3aed',
              flexShrink: 0,
            }}
          >
            <Clock style={{ width: '1.125rem', height: '1.125rem' }} />
          </span>
          <h3 style={{ fontSize: '1.125rem', fontWeight: 600 }}>Rate limit reached</h3>
        </div>

        <p style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.75rem' }}>{message}</p>

        <p style={{ fontSize: '0.875rem', color: '#374151', marginBottom: '1rem' }}>
          {remaining > 0 ? (
            <>
              You can try again in{' '}
              <span style={{ fontWeight: 600, color: '#7c3aed' }}>{remaining}s</span>.
            </>
          ) : (
            <span style={{ fontWeight: 600, color: '#16a34a' }}>You can try again now.</span>
          )}
        </p>

        <button
          onClick={() => hideRateLimitModal()}
          style={{
            width: '100%',
            padding: '0.5rem 0.75rem',
            backgroundColor: '#7c3aed',
            color: 'white',
            fontSize: '0.875rem',
            fontWeight: 500,
            borderRadius: '0.5rem',
            border: 'none',
            cursor: 'pointer',
          }}
        >
          Got it
        </button>
      </div>
    </div>
  );
}
