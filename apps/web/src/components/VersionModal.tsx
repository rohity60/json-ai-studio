'use client';

import { useState, useEffect } from 'react';
import { useSession } from '@/context/SessionContext';

// Module-level store for modal state — accessible from anywhere without prop drilling
let _pendingVersion: any = null;
let _listeners: Array<() => void> = [];

export function showVersionModal(version: any) {
  _pendingVersion = version;
  for (const listener of _listeners) listener();
}

export function hideVersionModal() {
  _pendingVersion = null;
  for (const listener of _listeners) listener();
}

export default function VersionModal() {
  const { selectVersion } = useSession();
  const [version, setVersion] = useState<any>(null);

  useEffect(() => {
    const handler = () => {
      setVersion(_pendingVersion);
    };
    _listeners.push(handler);
    return () => {
      _listeners = _listeners.filter((l) => l !== handler);
    };
  }, []);

  useEffect(() => {
    if (version) setVersion(_pendingVersion);
  }, [version]);

  if (!version) return null;

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
        onClick={() => hideVersionModal()}
      >
        <div
          style={{
            backgroundColor: 'white',
            borderRadius: '0.75rem',
            boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
            padding: '1.5rem',
            width: '100%',
            maxWidth: '20rem',
            marginLeft: '1rem',
            marginRight: '1rem',
            border: '1px solid #e5e7eb',
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <h3 style={{ fontSize: '1.125rem', fontWeight: 600, marginBottom: '0.5rem' }}>
            Switch to this version?
          </h3>
          <p style={{ fontSize: '0.875rem', color: '#6b7280', marginBottom: '1rem' }}>
            This will replace your current working JSON with the selected version.
          </p>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              onClick={() => {
                selectVersion(version);
                hideVersionModal();
              }}
              style={{
                flex: 1,
                padding: '0.375rem 0.75rem',
                backgroundColor: '#7c3aed',
                color: 'white',
                fontSize: '0.875rem',
                borderRadius: '0.5rem',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              Proceed
            </button>
            <button
              onClick={hideVersionModal}
              style={{
                flex: 1,
                padding: '0.375rem 0.75rem',
                border: '1px solid #d1d5db',
                fontSize: '0.875rem',
                borderRadius: '0.5rem',
                cursor: 'pointer',
                backgroundColor: 'white',
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
  );
}
