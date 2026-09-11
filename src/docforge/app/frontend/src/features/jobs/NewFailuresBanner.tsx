// ====== Code Summary ======
// The "X new failures since your last visit" bar — discreet (a thin inline strip, not a modal),
// clickable straight into the Failed tab. Renders nothing at count 0, closing the SRE persona's
// "no alerting/notifications anywhere" gap without a new alerting subsystem.

import { theme } from "../../theme";
import { useNewFailuresBanner } from "./state/useNewFailuresBanner";

interface NewFailuresBannerProps {
  onViewFailures: () => void;
}

export function NewFailuresBanner({ onViewFailures }: NewFailuresBannerProps) {
  const { count, dismiss } = useNewFailuresBanner();
  if (count === 0) return null;

  return (
    <button
      type="button"
      onClick={() => { onViewFailures(); dismiss(); }}
      style={{
        display: "flex", alignItems: "center", gap: theme.space.s, width: "100%", textAlign: "left",
        background: theme.color.errorSoft, border: `1px solid ${theme.color.error}`, borderRadius: theme.radius.m,
        padding: `${theme.space.s}px ${theme.space.m}px`, marginBottom: theme.space.l, cursor: "pointer",
        color: theme.color.errorStrong, fontSize: theme.font.size.s, fontWeight: theme.font.weight.semibold,
      }}
    >
      {count} new failure{count === 1 ? "" : "s"} since your last visit — view failed jobs
    </button>
  );
}
