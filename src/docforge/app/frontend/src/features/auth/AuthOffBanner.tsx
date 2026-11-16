// ====== Code Summary ======
// The "no auth is actually enforced" notice for the API-keys surface — shown whenever
// `useAuthEnabled()` resolves to `false` (never on `null`/unknown, per its own contract). Painted in
// the error/danger tone (never orange, which reads as "active/OK" per brand.md) since an anonymous
// visitor holding full admin access is a real exposure, not a neutral deployment fact. It shares
// `components/WarningGlyph` with TokenControl's auth-off badge.

import { WarningGlyph } from "../../components/WarningGlyph";
import { theme } from "../../theme";

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
