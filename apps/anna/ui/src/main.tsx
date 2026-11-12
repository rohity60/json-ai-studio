import React from 'react';
import { createRoot } from 'react-dom/client';
import { Toaster } from 'sonner';

import '@/app/globals.css';
import { SessionProvider } from '@/context/SessionContext';
import RateLimitModal from '@/components/RateLimitModal';
import TooLargeModal from '@/components/TooLargeModal';

import App from './App';
import { listDocs } from './anna/api';
import { connect } from './anna/runtime';
import { ensureLocalStorage } from './shims/storage';

const SESSION_KEY = 'json-ai-studio-session';

function showFatal(message: string) {
  const root = document.getElementById('root')!;
  root.textContent = message;
  root.style.cssText = 'padding:24px;font:14px system-ui,sans-serif;color:#374151';
}

/** The shared session code resumes the document named in localStorage. On
 *  a new device that is empty, so point it at the user's most recent
 *  document, which lives in their Anna storage. */
async function resumeLatestDocument() {
  if (localStorage.getItem(SESSION_KEY)) return;
  try {
    const [latest] = await listDocs();
    if (latest?.id) localStorage.setItem(SESSION_KEY, JSON.stringify({ sessionId: latest.id }));
  } catch {
    // No documents yet, or storage unreachable: start empty.
  }
}

async function start() {
  ensureLocalStorage();
  let anna: any;
  try {
    anna = await connect();
  } catch {
    showFatal('JSON AI Studio runs inside Anna. Open it from your Anna apps.');
    return;
  }
  anna.window?.set_title?.({ title: 'JSON AI Studio' }).catch(() => {});
  await resumeLatestDocument();

  createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <SessionProvider>
        <App />
        <Toaster position="top-right" />
        <RateLimitModal />
        <TooLargeModal />
      </SessionProvider>
    </React.StrictMode>,
  );
}

start();
