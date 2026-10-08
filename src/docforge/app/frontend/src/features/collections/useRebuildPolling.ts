// ====== Code Summary ======
// While an index rebuild is running, re-invokes `refetch` on a fixed cadence so the owning page
// learns when `needs_reindex` clears (the banner then unmounts). The rebuild is an async worker job,
// so one refetch right after queuing always still reads "needs reindex". Gives up after a cap so a
// failed job does not poll forever.

import { useEffect, useRef } from "react";

export const REBUILD_POLL_INTERVAL_MS = 3000;
export const REBUILD_POLL_MAX_TICKS = 100;

export function useRebuildPolling(active: boolean, refetch: (() => void) | undefined, onGiveUp: () => void): void {
  // Latest-callback refs: callers pass inline arrows, which must not restart the timer each render.
  const refetchRef = useRef(refetch);
  const giveUpRef = useRef(onGiveUp);
  refetchRef.current = refetch;
  giveUpRef.current = onGiveUp;
  const enabled = active && refetch !== undefined;

  useEffect(() => {
    if (!enabled) return undefined;
    let ticks = 0;
    const timer = window.setInterval(() => {
      ticks += 1;
      refetchRef.current?.();
      if (ticks >= REBUILD_POLL_MAX_TICKS) {
        window.clearInterval(timer);
        giveUpRef.current();
      }
    }, REBUILD_POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [enabled]);
}
