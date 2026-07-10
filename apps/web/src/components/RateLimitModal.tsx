'use client';

import { useState, useEffect } from 'react';
import { Clock } from 'lucide-react';

// Module-level store for modal state — callable from anywhere (context, api
// callbacks) without prop drilling. Same pattern as VersionModal.
export type RateLimitInfo = {
  message?: string;
  retryAfter?: number; // seconds until the caller may retry
  scope?: string; // "api" | "model"
  kind?: 'rate' | 'credits' | 'busy'; // credits = monthly quota exhausted (402), no countdown; busy = deployment/provider failure (503)
  loginAvailable?: boolean; // anonymous caller — logging in raises free limits
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

  const isCredits = info.kind === 'credits';
  const isBusy = info.kind === 'busy';
  const title = isCredits
    ? 'Free credits used up'
    : isBusy
      ? 'Service busy'
      : 'Rate limit reached';
  const message =
    info.message ||
    (isCredits
      ? "You've used up the free credits for this month."
      : isBusy
        ? 'The service is experiencing flaky behavior due to high load. Please try again in a few moments.'
        : "You've hit the rate limit. Please wait a moment before trying again.");

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
          <h3 style={{ fontSize: '1.125rem', fontWeight: 600 }}>{title}</h3>
        </div>

        <p style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '0.75rem' }}>{message}</p>

        {!isCredits && (
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
        )}

        {info.loginAvailable && (
          <button
            onClick={() => {
              window.location.href = '/auth/login?returnTo=/studio';
            }}
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
              marginBottom: '0.5rem',
            }}
          >
            Log in for higher free limits
          </button>
        )}

        <button
          onClick={() => hideRateLimitModal()}
          style={{
            width: '100%',
            padding: '0.5rem 0.75rem',
            backgroundColor: info.loginAvailable ? '#f3f4f6' : '#7c3aed',
            color: info.loginAvailable ? '#374151' : 'white',
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
