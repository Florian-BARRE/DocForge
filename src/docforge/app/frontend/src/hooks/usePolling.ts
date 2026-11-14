// ====== Code Summary ======
// Shared "fetch, then re-arm a timer" poll loop — replaces the hand-rolled
// `let cancelled / let timer / load() { fetch().then(arm).catch(arm) }` effect that every live
// tile, panel and fleet hook used to copy. The loop fetches once on (re)start, then re-arms a
// setTimeout `intervalMs` after each settled fetch (success, and by default failure too — so a
// transient blip never kills an always-live view). It stops on unmount / deps change (cancel flag,
// timer cleared, AbortSignal aborted) and, when `isDone` says so, after a terminal result.
// Errors are NOT surfaced by default: a caller that wants them passes `onError` (typically
// `setError(errorMessage(e))`); with no `onError` a failed tick is swallowed and polling continues.

// ====== Third-Party Library Imports ======
import { useEffect, type DependencyList } from "react";

export interface PollingOptions<T> {
  /** Delay between the end of one fetch and the start of the next. */
  intervalMs: number;
  /** Poll only while true (default true). Disabled -> nothing is fetched, no timer is armed. */
  enabled?: boolean;
  /** Called with each successful result, unless the loop was cancelled meanwhile. */
  onData?: (data: T) => void;
  /** Called with each failure, unless cancelled. Omit to swallow failures silently. */
  onError?: (error: unknown) => void;
  /** Return true on a result to stop polling (terminal status, settled batch). */
  isDone?: (data: T) => boolean;
  /** Keep polling after a failed fetch (default true); false stops the loop on the first error. */
  retryOnError?: boolean;
  /** Runs synchronously each time the loop (re)starts, before any fetch — even when disabled. */
  onReset?: () => void;
  /** Runs right before every fetch; `isPoll` is false for the first fetch of a (re)start. */
  onFetchStart?: (isPoll: boolean) => void;
  /** Runs after every fetch settles (success or failure), unless cancelled. */
  onSettled?: () => void;
}

/**
 * Polls `fetcher` while mounted. The loop restarts whenever `deps` change (list every value the
 * fetcher reads, like a useEffect dependency list); `options` and `fetcher` are read as of the
 * render that (re)started the loop, so inline closures do not restart it.
 *
 * @param fetcher Performs one fetch; receives an AbortSignal aborted when the loop stops.
 * @param options Cadence, enabling, result/error callbacks and stop conditions.
 * @param deps Dependency list restarting the loop.
 */
export function usePolling<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  options: PollingOptions<T>,
  deps: DependencyList,
): void {
  const { intervalMs, enabled = true } = options;

  useEffect(() => {
    const { onData, onError, isDone, retryOnError = true, onReset, onFetchStart, onSettled } = options;
    onReset?.();
    if (!enabled) return undefined;

    let cancelled = false;
    let timer: number | undefined;
    const controller = new AbortController();

    const load = (isPoll: boolean) => {
      onFetchStart?.(isPoll);
      fetcher(controller.signal)
        .then((data) => {
          if (cancelled) return;
          onData?.(data);
          if (!isDone?.(data)) timer = window.setTimeout(() => load(true), intervalMs);
        })
        .catch((error) => {
          if (cancelled) return;
          onError?.(error);
          if (retryOnError) timer = window.setTimeout(() => load(true), intervalMs);
        })
        .finally(() => {
          if (!cancelled) onSettled?.();
        });
    };
    load(false);

    return () => {
      cancelled = true;
      controller.abort();
      window.clearTimeout(timer);
    };
    // The caller owns the restart conditions through `deps`; `fetcher`/`options` are intentionally
    // not listed (inline closures would otherwise restart the loop every render).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, enabled, ...deps]);
}
