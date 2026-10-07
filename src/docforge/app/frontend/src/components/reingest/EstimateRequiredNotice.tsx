// ====== Code Summary ======
// The cost summary shown when a large reingest was refused 409 `estimate_required`: documents,
// cost (a lower bound when some stages are unpriced) and the estimator's caveats. The caller owns
// the "Confirm and reingest" button.

import type { EstimateRequired } from "../../api/reingest";
import { theme } from "../../theme";

function formatUsd(value: number): string {
  return `$${value.toFixed(value >= 1 ? 2 : 4)}`;
}

export function EstimateRequiredNotice({ info }: { info: EstimateRequired }) {
  const { estimate } = info;
  const mono = { fontFamily: theme.font.mono, color: theme.color.text } as const;
  return (
    <div
      role="alert"
      style={{
        display: "flex", flexDirection: "column", gap: theme.space.xs, fontSize: theme.font.size.s,
        color: theme.color.dim, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.m, padding: theme.space.s,
      }}
    >
      <span>{info.message}</span>
      <span>
        <span style={mono}>{info.matched.toLocaleString()}</span> documents
        {info.threshold > 0 && <> (confirmation required above <span style={mono}>{info.threshold.toLocaleString()}</span>)</>}
      </span>
      {estimate ? (
        <>
          <span>
            Estimated cost:{" "}
            <span style={mono}>
              {estimate.cost_complete ? formatUsd(estimate.total_cost_usd) : `at least ${formatUsd(estimate.total_cost_lower_bound_usd)}`}
            </span>
            {!estimate.cost_complete && " — some stages are unpriced"}
          </span>
          {estimate.caveats.length > 0 && (
            <ul style={{ margin: 0, paddingLeft: theme.space.l }}>
              {estimate.caveats.map((caveat) => <li key={caveat}>{caveat}</li>)}
            </ul>
          )}
        </>
      ) : (
        <span>No cost estimate is available.</span>
      )}
    </div>
  );
}
