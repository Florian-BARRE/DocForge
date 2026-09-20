// ====== Code Summary ======
// Overview's search-operational-health cockpit tile — mirrors WorkersStatusTile/QueueStatusTile's
// self-contained fetch+poll shape. Cumulative fleet-wide search stats (since process start), not a
// per-collection metric, so it sits with its deployment-wide operational-health peers rather than
// under any single collection. No canonical detail page exists for search health yet, so (like
// CollectionsStatusTiles' siblings before Collections grew health presets) it stays a pure summary —
// `onNavigate` is still accepted to keep HomePage's tile row call sites uniform.

import { useEffect, useState } from "react";
import { getSearchHealth, type SearchHealthSummary } from "../../api/search";
import { StatTile, type StatTileTone } from "../../components/StatTile";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";

const POLL_MS = 10000;

interface SearchHealthTileProps {
  onNavigate: Navigate;
}

/** Renders one "label value" pair inside the caption, with the value in mono per brand.md (machine
 *  values — counts, percents, timings — never prose in mono). */
function MonoStat({ label, value }: { label: string; value: string }) {
  return (
    <span>
      {label} <span style={{ fontFamily: theme.font.mono }}>{value}</span>
    </span>
  );
}

/** Formats a latency in ms as "962 ms" under a second, else "1.24 s" — matches the job-duration
 *  convention elsewhere in the cockpit (seconds once the number stops being glanceable in ms). */
function formatLatency(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

function formatPercent(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}

/** error_rate/zero_result_rate drive the tone exactly like RecentFailuresTile's own error/ok split
 *  — a live error rate outranks a zero-hit rate, which outranks a clean "ok". */
function toneFor(data: SearchHealthSummary): StatTileTone {
  if (data.error_rate > 0) return "error";
  if (data.zero_result_rate > 0) return "warn";
  return "ok";
}

export function SearchHealthTile({ onNavigate: _onNavigate }: SearchHealthTileProps) {
  const [data, setData] = useState<SearchHealthSummary | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;

    const load = () => {
      getSearchHealth()
        .then((next) => {
          if (cancelled) return;
          setData(next);
          timer = window.setTimeout(load, POLL_MS);
        })
        .catch(() => {
          if (!cancelled) timer = window.setTimeout(load, POLL_MS);
        });
    };
    load();

    return () => { cancelled = true; window.clearTimeout(timer); };
  }, []);

  if (!data) return <StatTile value="…" label="Search health" />;

  if (data.total_runs === 0) {
    return <StatTile value="—" label="Search health" tone="neutral" caption="No searches yet" />;
  }

  return (
    <StatTile
      value={data.total_runs}
      label="Searches run"
      tone={toneFor(data)}
      caption={
        <>
          <MonoStat label="p95" value={formatLatency(data.p95_latency_ms)} /> ·{" "}
          <MonoStat label="zero-hit" value={formatPercent(data.zero_result_rate)} /> ·{" "}
          <MonoStat label="errors" value={formatPercent(data.error_rate)} />
        </>
      }
    />
  );
}
