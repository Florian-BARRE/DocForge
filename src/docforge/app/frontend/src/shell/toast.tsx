// ====== Code Summary ======
// A tiny toast system: a provider that owns the queue, a `useToast()` hook every feature calls to
// signal an event (saved, ingestion launched, deleted, failed…), and a fixed bottom-right host that
// stacks the toasts, auto-dismisses them, and lets them be closed. Themed via tokens; entrance
// animation lives in index.css and honours prefers-reduced-motion.

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

const DISMISS_MS = 4200;

const TONE: Record<ToastTone, { accent: string; soft: string; glyph: string }> = {
  success: { accent: t.color.ok, soft: t.color.okSoft, glyph: "✓" },
  error: { accent: t.color.error, soft: t.color.errorSoft, glyph: "!" },
  info: { accent: t.color.accent, soft: t.color.accentSoft, glyph: "→" },
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(0);

  const remove = useCallback((id: number) => setItems((list) => list.filter((it) => it.id !== id)), []);

  const push = useCallback(
    (tone: ToastTone, message: string) => {
      const id = (nextId.current += 1);
      setItems((list) => [...list, { id, tone, message }]);
      window.setTimeout(() => remove(id), DISMISS_MS);
    },
    [remove],
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
          return (
            <div
              key={item.id}
              className="df-toast"
              role="status"
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
