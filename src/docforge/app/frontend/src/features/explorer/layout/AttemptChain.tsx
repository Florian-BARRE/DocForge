// ====== Code Summary ======
// The model-chain trace of one enrichment, rendered as an ordered row of pills: each model that was
// tried (provider · model, with latency), in escalation order, separated by "›". A failed attempt
// reads in error ink with a strikethrough and its reason on hover; the model that succeeded reads in
// done ink. This is the concrete answer to "enriched by which model / OCR, and what escalated first".

import type { IRAttempt } from "../../../api/explorer";
import { theme } from "../../../theme";

interface AttemptChainProps {
  attempts: IRAttempt[];
}

function AttemptPill({ attempt }: { attempt: IRAttempt }) {
  const failed = attempt.status !== "ok";
  const ink = failed ? theme.color.errorStrong : theme.color.okStrong;
  const bg = failed ? theme.color.errorSoft : theme.color.okSoft;
  return (
    <span
      title={attempt.error ?? undefined}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "1px 6px",
        borderRadius: theme.radius.s,
        background: bg,
        color: ink,
        fontFamily: theme.font.mono,
        fontSize: theme.font.size.xs,
        textDecoration: failed ? "line-through" : "none",
      }}
    >
      <span>
        {attempt.provider_id} · {attempt.model}
      </span>
      {attempt.latency_ms != null && (
        <span style={{ color: theme.color.mute }}>{attempt.latency_ms}ms</span>
      )}
    </span>
  );
}

export function AttemptChain({ attempts }: AttemptChainProps) {
  if (!attempts.length) return null;

  const ordered = [...attempts].sort((a, b) => a.position - b.position);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
      {ordered.map((attempt, index) => (
        <span key={index} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
          {index > 0 && <span style={{ color: theme.color.mute, fontSize: theme.font.size.xs }}>›</span>}
          <AttemptPill attempt={attempt} />
        </span>
      ))}
    </div>
  );
}
