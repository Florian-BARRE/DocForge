// ====== Code Summary ======
// The "X new failures since your last visit" cursor — a localStorage-persisted timestamp, best-effort
// (try/catch, same pattern as useSidebarPin) since a private-browsing storage error must never break
// the page. First-ever visit seeds the cursor at "now" so a brand-new deployment doesn't dump its
// entire failure history as "new"; every visit after that only counts failures past the last dismiss.

import { useState } from "react";
import { getNewFailures } from "../../../api/jobs";
import { usePolling } from "../../../hooks/usePolling";

const STORAGE_KEY = "docforge_jobs_last_seen_failures_at";
const POLL_MS = 30000;

function readCursor(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

function writeCursor(value: string): void {
  try {
    localStorage.setItem(STORAGE_KEY, value);
  } catch {
    // Unavailable storage — the banner just re-shows every reload, never a hard failure.
  }
}

export interface NewFailuresBannerState {
  count: number;
  /** Advances the cursor to the latest known failure (or now, if there is none) and clears the count. */
  dismiss: () => void;
}

export function useNewFailuresBanner(): NewFailuresBannerState {
  const [cursor, setCursor] = useState<string>(() => {
    const existing = readCursor();
    if (existing) return existing;
    const now = new Date().toISOString();
    writeCursor(now);
    return now;
  });
  const [count, setCount] = useState(0);
  const [latestFailedAt, setLatestFailedAt] = useState<string | null>(null);

  usePolling(
    () => getNewFailures({ since: cursor }),
    {
      intervalMs: POLL_MS,
      onData: (next) => { setCount(next.count); setLatestFailedAt(next.latest_failed_at); },
    },
    [cursor],
  );

  const dismiss = () => {
    const next = latestFailedAt ?? new Date().toISOString();
    writeCursor(next);
    setCursor(next);
    setCount(0);
  };

  return { count, dismiss };
}
