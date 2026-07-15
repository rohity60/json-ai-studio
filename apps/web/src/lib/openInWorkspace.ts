'use client';

/** Open-in-Workspace handoff (ADR-0020). Seeds a session from a template,
 *  then routes to /studio. Hands off via the SAME localStorage keys the
 *  SessionProvider already restores from — no changes to the fragile
 *  hydrate effect, no global `loading` flag involved. */

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { seedFromTemplate } from '@/lib/api';
import { getAnonApiKey } from '@/lib/anonKey';
import type { TemplateMeta } from '@/content/types';

const SESSION_KEY = 'json-ai-studio-session';
const PROMPTS_KEY = 'json-ai-studio-starter-prompts';

/** Read the one-shot starter prompts stashed before navigation WITHOUT
 *  clearing them. Non-destructive so React StrictMode's double-invoked mount
 *  effect reads the same value both times. Call clearStarterPrompts() once the
 *  user acts on them. */
export function peekStarterPrompts(): string[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = sessionStorage.getItem(PROMPTS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((x) => typeof x === 'string') : [];
  } catch {
    return [];
  }
}

export function clearStarterPrompts() {
  if (typeof window !== 'undefined') sessionStorage.removeItem(PROMPTS_KEY);
}

export function useOpenInWorkspace() {
  const router = useRouter();
  const [pending, setPending] = useState<string | null>(null);

  const open = useCallback(
    async (meta: TemplateMeta, json: unknown, presetPrompt = '', tag = 'open') => {
      setPending(tag);
      const prompts = [presetPrompt, ...meta.starterPrompts].filter(Boolean);
      try {
        const res = await seedFromTemplate(
          meta.slug,
          meta.title,
          json,
          prompts,
          getAnonApiKey(),
        );
        localStorage.setItem(SESSION_KEY, JSON.stringify({ sessionId: res.id }));
        sessionStorage.setItem(PROMPTS_KEY, JSON.stringify(res.starter_prompts));
        router.push('/studio');
      } catch (err: any) {
        setPending(null);
        toast.error(String(err?.message || err));
      }
    },
    [router],
  );

  return { open, pending };
}
