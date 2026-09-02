// ====== Code Summary ======
// The top bar's API token control — paste/save/clear the Bearer token used by every request (see
// `apiFetch` in api/http.ts). Collapsed to a single button by default so it stays unobtrusive;
// expands into an inline field on click. The token itself is never displayed once saved.
//
// The trigger reads a currentColor key glyph, never an emoji. Below ~480px the "Token"/"Token
// set" label hides (icon + the border colour already carry the state), which is one of the
// widths saved by collapsing the top bar so the whole app stops scrolling horizontally on mobile.

import { useEffect, useState } from "react";
import { API_TOKEN_CLEARED_EVENT, clearApiToken, getApiToken, setApiToken } from "../api/http";
import { theme } from "../theme";

const RESPONSIVE_LABEL_CSS = `
  @media (max-width: 480px) {
    .df-token-label { display: none; }
  }
`;

function KeyGlyph() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />
    </svg>
  );
}

export function TokenControl() {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [hasToken, setHasToken] = useState(() => Boolean(getApiToken()));

  // A request can clear the token from outside this component (a 401 response — see api/http.ts),
  // so the pill must react to that too, not just its own `clear()` button.
  useEffect(() => {
    const onCleared = () => setHasToken(false);
    window.addEventListener(API_TOKEN_CLEARED_EVENT, onCleared);
    return () => window.removeEventListener(API_TOKEN_CLEARED_EVENT, onCleared);
  }, []);

  const save = () => {
    const value = draft.trim();
    if (!value) return;
    setApiToken(value);
    setHasToken(true);
    setDraft("");
    setOpen(false);
  };

  const clear = () => {
    clearApiToken();
    setHasToken(false);
    setDraft("");
  };

  if (!open) {
    return (
      <>
        <style>{RESPONSIVE_LABEL_CSS}</style>
        <button
          onClick={() => setOpen(true)}
          title={hasToken ? "API token set" : "No API token set"}
          style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            background: "none", border: `1px solid ${hasToken ? theme.color.ok : theme.color.line}`,
            color: hasToken ? theme.color.ok : theme.color.dim,
            borderRadius: theme.radius.s, padding: "5px 10px",
            fontSize: theme.font.size.m, cursor: "pointer",
          }}
        >
          <KeyGlyph />
          <span className="df-token-label">{hasToken ? "Token set" : "Token"}</span>
        </button>
      </>
    );
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: theme.space.xs }}>
      <input
        type="password"
        autoFocus
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") save();
          if (e.key === "Escape") setOpen(false);
        }}
        placeholder="paste API token…"
        style={{
          background: theme.color.bg, border: `1px solid ${theme.color.line}`,
          borderRadius: theme.radius.s, padding: "4px 7px",
          fontSize: theme.font.size.m, color: theme.color.text, width: 180,
        }}
      />
      <button
        onClick={save}
        style={{
          background: theme.color.accent, color: theme.color.onAccent, border: "none",
          borderRadius: theme.radius.s, padding: "5px 10px", fontSize: theme.font.size.m, cursor: "pointer",
        }}
      >
        save
      </button>
      {hasToken && (
        <button
          onClick={clear}
          style={{
            background: "none", color: theme.color.error, border: `1px solid ${theme.color.error}`,
            borderRadius: theme.radius.s, padding: "5px 10px", fontSize: theme.font.size.m, cursor: "pointer",
          }}
        >
          clear
        </button>
      )}
      <button
        onClick={() => setOpen(false)}
        style={{
          background: "none", color: theme.color.dim, border: "none",
          fontSize: theme.font.size.m, cursor: "pointer",
        }}
      >
        ✕
      </button>
    </div>
  );
}
