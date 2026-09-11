// ====== Code Summary ======
// The "no auth is actually enforced" notice for the API-keys surface — shown whenever
// `useAuthEnabled()` resolves to `false` (never on `null`/unknown, per its own contract). Painted in
// the error/danger tone (never orange, which reads as "active/OK" per brand.md) since an anonymous
// visitor holding full admin access is a real exposure, not a neutral deployment fact. `WarningGlyph`
// is exported so TokenControl's auth-off badge carries the same glyph.

import { theme } from "../../theme";

export function WarningGlyph() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  );
}

export function AuthOffBanner() {
  return (
    <div
      style={{
        display: "flex", flexDirection: "column", gap: theme.space.xs,
        background: theme.color.errorSoft, border: `1px solid ${theme.color.error}`,
        borderRadius: theme.radius.l, padding: theme.space.l, marginBottom: theme.space.l,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: theme.space.s, color: theme.color.errorStrong }}>
        <WarningGlyph />
        <span style={{ fontFamily: theme.font.display, fontWeight: theme.font.weight.bold, fontSize: theme.font.size.l }}>
          Authentication is disabled
        </span>
      </div>
      <span style={{ color: theme.color.text, fontSize: theme.font.size.s }}>
        API keys are not enforced on this deployment — anyone reaching this UI already has full admin
        access, so key management is inert and hidden below. Set <code>AUTH_ENABLED</code> and{" "}
        <code>AUTH_ROOT_TOKEN</code> and recreate the app to manage keys.
      </span>
    </div>
  );
}
