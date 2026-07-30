// ====== Code Summary ======
// The top bar's API token control — paste/save/clear the Bearer token used by every request (see
// `apiFetch` in api/http.ts). Collapsed to a single button by default so it stays unobtrusive;
// expands into an inline field on click. The token itself is never displayed once saved.

import { useEffect, useState } from "react";
import { API_TOKEN_CLEARED_EVENT, clearApiToken, getApiToken, setApiToken } from "../api/http";
import { theme } from "../theme";

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
      <button
        onClick={() => setOpen(true)}
        title={hasToken ? "API token set" : "No API token set"}
        style={{
          background: "none", border: `1px solid ${hasToken ? theme.color.ok : theme.color.line}`,
          color: hasToken ? theme.color.ok : theme.color.dim,
          borderRadius: theme.radius.s, padding: "5px 10px",
          fontSize: theme.font.size.m, cursor: "pointer",
        }}
      >
        🔑 {hasToken ? "Token set" : "Token"}
      </button>
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
