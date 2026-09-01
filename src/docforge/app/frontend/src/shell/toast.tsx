// ====== Code Summary ======
// A tiny toast system: a provider that owns the queue, a `useToast()` hook every feature calls to
// signal an event (saved, ingestion launched, deleted, failed…), and a fixed bottom-right host that
// stacks the toasts, auto-dismisses them, and lets them be closed. Themed via tokens; entrance
// animation lives in index.css and honours prefers-reduced-motion. Dismissal pauses on hover/focus
// (WCAG 2.2.1 — a reader must be able to stop a message from disappearing) and scales with message
// length so a long error doesn't outlive the time it takes to read it.

import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { theme as t } from "../theme";

type ToastTone = "success" | "error" | "info";

interface ToastItem {
  id: number;
  tone: ToastTone;
  message: string;
}

export interface ToastApi {
  push: (tone: ToastTone, message: string) => void;
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

/** Signal a user-facing event as a toast. Safe to call from any component under <ToastProvider>. */
export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) throw new Error("useToast must be used within a <ToastProvider>");
  return api;
}

// Floor for every toast, and the per-character allowance used to stretch it for longer messages —
// roughly a 20 chars/sec reading pace, so a one-liner still just gets the floor.
const DISMISS_MS = 4200;
const MS_PER_CHAR = 50;

function dismissDelay(message: string): number {
  return Math.max(DISMISS_MS, message.length * MS_PER_CHAR);
}

const TONE: Record<ToastTone, { accent: string; soft: string; glyph: string }> = {
  success: { accent: t.color.ok, soft: t.color.okSoft, glyph: "✓" },
  error: { accent: t.color.error, soft: t.color.errorSoft, glyph: "!" },
  info: { accent: t.color.accent, soft: t.color.accentSoft, glyph: "→" },
};

/** Per-toast pause/resume bookkeeping — kept in a ref so hover/focus never triggers a rerender. */
interface TimerHandle {
  timeoutId: number | null;
  remainingMs: number;
  startedAt: number;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(0);
  const timers = useRef(new Map<number, TimerHandle>());

  const remove = useCallback((id: number) => {
    const handle = timers.current.get(id);
    if (handle?.timeoutId != null) window.clearTimeout(handle.timeoutId);
    timers.current.delete(id);
    setItems((list) => list.filter((it) => it.id !== id));
  }, []);

  const startTimer = useCallback(
    (id: number, remainingMs: number) => {
      const timeoutId = window.setTimeout(() => remove(id), remainingMs);
      timers.current.set(id, { timeoutId, remainingMs, startedAt: Date.now() });
    },
    [remove],
  );

  const pauseTimer = useCallback((id: number) => {
    const handle = timers.current.get(id);
    if (!handle || handle.timeoutId == null) return;
    window.clearTimeout(handle.timeoutId);
    const elapsed = Date.now() - handle.startedAt;
    timers.current.set(id, {
      timeoutId: null,
      remainingMs: Math.max(0, handle.remainingMs - elapsed),
      startedAt: handle.startedAt,
    });
  }, []);

  const resumeTimer = useCallback(
    (id: number) => {
      const handle = timers.current.get(id);
      if (!handle || handle.timeoutId != null || handle.remainingMs <= 0) return;
      startTimer(id, handle.remainingMs);
    },
    [startTimer],
  );

  const push = useCallback(
    (tone: ToastTone, message: string) => {
      const id = (nextId.current += 1);
      setItems((list) => [...list, { id, tone, message }]);
      startTimer(id, dismissDelay(message));
    },
    [startTimer],
  );

  const api = useMemo<ToastApi>(
    () => ({
      push,
      success: (message) => push("success", message),
      error: (message) => push("error", message),
      info: (message) => push("info", message),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        style={{
          position: "fixed", right: t.space.l, bottom: t.space.l, zIndex: 1000,
          display: "flex", flexDirection: "column", gap: t.space.s, maxWidth: 380, pointerEvents: "none",
        }}
      >
        {items.map((item) => {
          const tone = TONE[item.tone];
          // Errors interrupt (assertive); success/info just get announced in turn (polite).
          const isError = item.tone === "error";
          return (
            <div
              key={item.id}
              className="df-toast"
              role={isError ? "alert" : "status"}
              aria-live={isError ? "assertive" : "polite"}
              tabIndex={-1}
              onMouseEnter={() => pauseTimer(item.id)}
              onMouseLeave={() => resumeTimer(item.id)}
              onFocus={() => pauseTimer(item.id)}
              onBlur={() => resumeTimer(item.id)}
              style={{
                pointerEvents: "auto", display: "flex", alignItems: "flex-start", gap: t.space.s,
                background: t.color.panel, border: `1px solid ${t.color.line}`,
                borderLeft: `3px solid ${tone.accent}`, borderRadius: t.radius.m,
                padding: `${t.space.s}px ${t.space.m}px`, boxShadow: t.shadow.pop,
              }}
            >
              <span
                aria-hidden
                style={{
                  flexShrink: 0, width: 18, height: 18, marginTop: 1, borderRadius: "50%",
                  background: tone.soft, color: tone.accent, fontSize: 12, fontWeight: 700,
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}
              >
                {tone.glyph}
              </span>
              <span style={{ flex: 1, color: t.color.text, fontSize: t.font.size.m, lineHeight: 1.35 }}>
                {item.message}
              </span>
              <button
                onClick={() => remove(item.id)}
                aria-label="Dismiss"
                style={{
                  flexShrink: 0, background: "none", border: "none", cursor: "pointer",
                  color: t.color.mute, fontSize: t.font.size.m, lineHeight: 1, padding: 0,
                }}
              >
                ✕
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}
