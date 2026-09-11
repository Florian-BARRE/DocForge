// ====== Code Summary ======
// The API token control — paste/save/clear the Bearer token used by every request (see `apiFetch`
// in api/http.ts). Collapsed to a single button by default so it stays unobtrusive; expands into an
// inline field on click. The token itself is never displayed once saved.
//
// The trigger reads a currentColor key glyph, never an emoji. Below ~480px the "Token"/"Token
// set" label hides (icon + the border colour already carry the state), which is one of the
// widths saved by collapsing the top bar so the whole app stops scrolling horizontally on mobile.
//
// `compact` renders a bare icon-only button instead (no label, no inline editor — there isn't
// room for one in the sidebar's ~72px collapsed rail): clicking it calls `onRequestExpand` so the
// caller can widen its own chrome first (the sidebar pins itself open) before the full control with
// its editor becomes reachable.

import { useEffect, useState } from "react";
import { API_TOKEN_CLEARED_EVENT, clearApiToken, getApiToken, setApiToken } from "../api/http";
import { WarningGlyph } from "../features/auth/AuthOffBanner";
import { useAuthEnabled } from "../features/auth/useAuthEnabled";
import { theme } from "../theme";

const AUTH_OFF_TITLE = "Authentication is disabled on this deployment — API keys are not enforced.";
const TOKEN_PREFIX = "df_";
const TOKEN_FORMAT_WARNING = `DocForge API keys normally start with "${TOKEN_PREFIX}" — double-check this value.`;

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

interface TokenControlProps {
  compact?: boolean;
  onRequestExpand?: () => void;
}

export function TokenControl({ compact = false, onRequestExpand }: TokenControlProps = {}) {
  const authEnabled = useAuthEnabled();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [hasToken, setHasToken] = useState(() => Boolean(getApiToken()));
  const authOff = authEnabled === false;

  // A request can clear the token from outside this component (a 401 response — see api/http.ts),
  // so the pill must react to that too, not just its own `clear()` button.
  useEffect(() => {
    const onCleared = () => setHasToken(false);
    window.addEventListener(API_TOKEN_CLEARED_EVENT, onCleared);
    return () => window.removeEventListener(API_TOKEN_CLEARED_EVENT, onCleared);
  }, []);

  if (compact) {
    return (
      <button
        onClick={onRequestExpand}
        title={authOff ? AUTH_OFF_TITLE : hasToken ? "API token set — expand sidebar to manage" : "No API token set — expand sidebar to add one"}
        aria-label="API token"
        style={{
          display: "grid", placeItems: "center", width: 30, height: 26, flexShrink: 0,
          background: "none", border: `1px solid ${authOff ? theme.color.error : hasToken ? theme.color.ok : theme.color.line}`,
          color: authOff ? theme.color.error : hasToken ? theme.color.ok : theme.color.dim,
          borderRadius: theme.radius.s, cursor: "pointer",
        }}
      >
        {authOff ? <WarningGlyph /> : <KeyGlyph />}
      </button>
    );
  }

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
          title={authOff ? AUTH_OFF_TITLE : hasToken ? "API token set" : "No API token set"}
          style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            background: "none", border: `1px solid ${authOff ? theme.color.error : hasToken ? theme.color.ok : theme.color.line}`,
            color: authOff ? theme.color.error : hasToken ? theme.color.ok : theme.color.dim,
            borderRadius: theme.radius.s, padding: "5px 10px",
            fontSize: theme.font.size.m, cursor: "pointer",
          }}
        >
          {authOff ? <WarningGlyph /> : <KeyGlyph />}
          <span className="df-token-label">{authOff ? "Auth off" : hasToken ? "Token set" : "Token"}</span>
        </button>
      </>
    );
  }

  const draftFormatWarning = draft.trim().length > 0 && !draft.trim().startsWith(TOKEN_PREFIX);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
      {authOff && <span style={{ color: theme.color.error, fontSize: theme.font.size.xs }}>{AUTH_OFF_TITLE}</span>}
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
      {draftFormatWarning && (
        <span style={{ color: theme.color.warn, fontSize: theme.font.size.xs }}>{TOKEN_FORMAT_WARNING}</span>
      )}
    </div>
  );
}
