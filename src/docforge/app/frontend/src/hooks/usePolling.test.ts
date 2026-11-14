// ====== Code Summary ======
// usePolling with fake timers: first load, re-arm after success and after error, stop on unmount,
// stop on a terminal result, disabled mode, restart on deps change, abort signal, error-free default.

// ====== Third-Party Library Imports ======
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// ====== Local Project Imports ======
import { errorMessage } from "./errorMessage";
import { usePolling, type PollingOptions } from "./usePolling";

const INTERVAL = 1000;

/** Lets the fetch promise chain settle without advancing the fake clock. */
async function flush() {
  await act(async () => { await Promise.resolve(); });
}

async function tick(ms = INTERVAL) {
  await act(async () => { await vi.advanceTimersByTimeAsync(ms); });
}

beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { vi.useRealTimers(); });

describe("usePolling", () => {
  it("fetches once immediately and delivers the data", async () => {
    const fetcher = vi.fn().mockResolvedValue("a");
    const onData = vi.fn();
    renderHook(() => usePolling(fetcher, { intervalMs: INTERVAL, onData }, []));
    expect(fetcher).toHaveBeenCalledTimes(1);
    await flush();
    expect(onData).toHaveBeenCalledWith("a");
  });

  it("re-arms after a success, one tick per interval", async () => {
    const fetcher = vi.fn().mockResolvedValue("a");
    renderHook(() => usePolling(fetcher, { intervalMs: INTERVAL }, []));
    await flush();
    await tick(INTERVAL - 1);
    expect(fetcher).toHaveBeenCalledTimes(1);
    await tick(1);
    expect(fetcher).toHaveBeenCalledTimes(2);
    await tick();
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it("re-arms after an error and reports it only to onError", async () => {
    const fetcher = vi.fn().mockRejectedValueOnce(new Error("boom")).mockResolvedValue("ok");
    const onData = vi.fn();
    const onError = vi.fn();
    renderHook(() => usePolling(fetcher, { intervalMs: INTERVAL, onData, onError }, []));
    await flush();
    expect(onError).toHaveBeenCalledTimes(1);
    expect(errorMessage(onError.mock.calls[0][0])).toBe("boom");
    expect(onData).not.toHaveBeenCalled();
    await tick();
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(onData).toHaveBeenCalledWith("ok");
  });

  it("swallows errors silently and keeps polling when no onError is given", async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error("boom"));
    renderHook(() => usePolling(fetcher, { intervalMs: INTERVAL }, []));
    await flush();
    await tick();
    await tick();
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it("stops after the first error with retryOnError false", async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error("boom"));
    renderHook(() => usePolling(fetcher, { intervalMs: INTERVAL, retryOnError: false }, []));
    await flush();
    await tick(INTERVAL * 5);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("stops re-arming once isDone sees a terminal result", async () => {
    const fetcher = vi.fn().mockResolvedValueOnce("running").mockResolvedValue("done");
    const onData = vi.fn();
    renderHook(() => usePolling(fetcher, { intervalMs: INTERVAL, onData, isDone: (s) => s === "done" }, []));
    await flush();
    await tick();
    expect(onData).toHaveBeenLastCalledWith("done");
    await tick(INTERVAL * 5);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("stops on unmount: no further fetch and a late response is ignored", async () => {
    let resolve!: (v: string) => void;
    const fetcher = vi.fn().mockImplementation(() => new Promise<string>((r) => { resolve = r; }));
    const onData = vi.fn();
    const { unmount } = renderHook(() => usePolling(fetcher, { intervalMs: INTERVAL, onData }, []));
    unmount();
    resolve("late");
    await flush();
    expect(onData).not.toHaveBeenCalled();
    await tick(INTERVAL * 5);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("clears the armed timer on unmount", async () => {
    const fetcher = vi.fn().mockResolvedValue("a");
    const { unmount } = renderHook(() => usePolling(fetcher, { intervalMs: INTERVAL }, []));
    await flush();
    unmount();
    await tick(INTERVAL * 5);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("aborts the signal handed to the fetcher on unmount", async () => {
    let signal: AbortSignal | undefined;
    const fetcher = vi.fn().mockImplementation((s: AbortSignal) => { signal = s; return new Promise(() => {}); });
    const { unmount } = renderHook(() => usePolling(fetcher, { intervalMs: INTERVAL }, []));
    expect(signal?.aborted).toBe(false);
    unmount();
    expect(signal?.aborted).toBe(true);
  });

  it("does not fetch while disabled, but still runs onReset", async () => {
    const fetcher = vi.fn().mockResolvedValue("a");
    const onReset = vi.fn();
    renderHook(() => usePolling(fetcher, { intervalMs: INTERVAL, enabled: false, onReset }, []));
    await tick(INTERVAL * 3);
    expect(onReset).toHaveBeenCalledTimes(1);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("restarts when deps change, cancelling the previous loop", async () => {
    const fetcher = vi.fn().mockResolvedValue("a");
    const onReset = vi.fn();
    const { rerender } = renderHook(({ id }) => usePolling(fetcher, { intervalMs: INTERVAL, onReset }, [id]), {
      initialProps: { id: 1 },
    });
    await flush();
    rerender({ id: 2 });
    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(onReset).toHaveBeenCalledTimes(2);
    await tick();
    expect(fetcher).toHaveBeenCalledTimes(3); // only the new loop re-armed
  });

  it("does not restart on a re-render with identical deps and inline options", async () => {
    const fetcher = vi.fn().mockResolvedValue("a");
    const { rerender } = renderHook(() => usePolling(fetcher, { intervalMs: INTERVAL, onData: () => {} } as PollingOptions<string>, []));
    await flush();
    rerender();
    rerender();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("reports isPoll=false for the first fetch of a start, then true, around onSettled", async () => {
    const fetcher = vi.fn().mockResolvedValue("a");
    const onFetchStart = vi.fn();
    const onSettled = vi.fn();
    renderHook(() => usePolling(fetcher, { intervalMs: INTERVAL, onFetchStart, onSettled }, []));
    await flush();
    await flush();
    expect(onSettled).toHaveBeenCalledTimes(1);
    await tick();
    expect(onFetchStart.mock.calls.map((c) => c[0])).toEqual([false, true]);
  });
});

describe("errorMessage", () => {
  it("returns an Error's message and stringifies anything else", () => {
    expect(errorMessage(new Error("x"))).toBe("x");
    expect(errorMessage("plain")).toBe("plain");
    expect(errorMessage(42)).toBe("42");
  });
});
