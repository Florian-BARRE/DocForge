// ====== Code Summary ======
// Characterization (safety net) of `streamJobEvents` (api/jobs.ts): the hand-rolled SSE reader that
// the polling-hook refactor (R-29) and the api split (R-31) must keep intact. Drives it with a fake
// ReadableStream and records frame parsing across chunk boundaries, garbled-frame skipping,
// event/status dispatch, the 401 / non-2xx rejections and abort propagation.

// ====== Third-Party Library Imports ======
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// ====== Local Project Imports ======
import { getApiToken, HttpError, setApiToken } from "./http";
import { streamJobEvents, type JobEvent, type JobStatus } from "./jobs";

const fetchMock = vi.fn();
const encoder = new TextEncoder();

beforeEach(() => {
  localStorage.clear();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

type Chunk = string | Uint8Array;

function streamOf(chunks: Chunk[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(typeof chunk === "string" ? encoder.encode(chunk) : chunk);
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

function frame(payload: unknown): string {
  return `data: ${JSON.stringify(payload)}\n\n`;
}

const EVENT = { frame: "event", stage: "parse", status: "done" };
const STATUS = { frame: "status", status: "running", progress: 0.5 };

/** Runs the stream over `chunks` and returns what the two handlers received, in order. */
async function collect(chunks: Chunk[]) {
  fetchMock.mockResolvedValueOnce(streamOf(chunks));
  const calls: Array<["event" | "status", unknown]> = [];
  await streamJobEvents("job-1", {
    onEvent: (e: JobEvent) => calls.push(["event", e]),
    onStatus: (s: JobStatus) => calls.push(["status", s]),
  });
  return calls;
}

describe("streamJobEvents — request", () => {
  it("opens GET /api/v1/jobs/{id}/stream asking for an event stream, without auth when no token", async () => {
    fetchMock.mockResolvedValueOnce(streamOf([]));
    await streamJobEvents("job-1", { onEvent: vi.fn(), onStatus: vi.fn() });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/jobs/job-1/stream");
    expect(init.headers).toEqual({ Accept: "text/event-stream" });
    expect(init.signal).toBeUndefined();
  });

  it("adds the Bearer header when a token is stored", async () => {
    setApiToken("tok");
    fetchMock.mockResolvedValueOnce(streamOf([]));
    await streamJobEvents("job-1", { onEvent: vi.fn(), onStatus: vi.fn() });
    expect(fetchMock.mock.calls[0][1].headers).toEqual({ Accept: "text/event-stream", Authorization: "Bearer tok" });
  });

  it("forwards the caller's abort signal to fetch", async () => {
    const controller = new AbortController();
    fetchMock.mockResolvedValueOnce(streamOf([]));
    await streamJobEvents("job-1", { onEvent: vi.fn(), onStatus: vi.fn(), signal: controller.signal });
    expect(fetchMock.mock.calls[0][1].signal).toBe(controller.signal);
  });
});

describe("streamJobEvents — frame dispatch", () => {
  it("resolves with no handler call for an empty stream", async () => {
    expect(await collect([])).toEqual([]);
  });

  it("dispatches an `event` frame to onEvent with the whole frame object", async () => {
    expect(await collect([frame(EVENT)])).toEqual([["event", EVENT]]);
  });

  it("dispatches a `status` frame to onStatus with the whole frame object", async () => {
    expect(await collect([frame(STATUS)])).toEqual([["status", STATUS]]);
  });

  it("delivers several frames of one chunk in order", async () => {
    const calls = await collect([frame(EVENT) + frame(STATUS) + frame({ ...EVENT, stage: "chunk" })]);
    expect(calls).toEqual([
      ["event", EVENT],
      ["status", STATUS],
      ["event", { ...EVENT, stage: "chunk" }],
    ]);
  });

  it("ignores a frame of unknown type", async () => {
    expect(await collect([frame({ frame: "other" }), frame({ stage: "no-frame-key" }), frame(EVENT)])).toEqual([
      ["event", EVENT],
    ]);
  });

  it("accepts `data:` with no space after the colon", async () => {
    expect(await collect([`data:${JSON.stringify(EVENT)}\n\n`])).toEqual([["event", EVENT]]);
  });

  it("finds the data line among other SSE fields of the same frame", async () => {
    const raw = `id: 7\nevent: update\ndata: ${JSON.stringify(STATUS)}\n\n`;
    expect(await collect([raw])).toEqual([["status", STATUS]]);
  });

  it("skips a frame with no data line (a comment / keep-alive)", async () => {
    expect(await collect([": keep-alive\n\n", frame(EVENT)])).toEqual([["event", EVENT]]);
  });

  it("uses only the first data line of a multi-data-line frame", async () => {
    const raw = `data: ${JSON.stringify(EVENT)}\ndata: ${JSON.stringify(STATUS)}\n\n`;
    expect(await collect([raw])).toEqual([["event", EVENT]]);
  });
});

describe("streamJobEvents — chunk boundaries", () => {
  it("reassembles a frame split mid-JSON across two chunks", async () => {
    const raw = frame(EVENT);
    expect(await collect([raw.slice(0, 14), raw.slice(14)])).toEqual([["event", EVENT]]);
  });

  it("reassembles a frame whose blank-line separator is split between chunks", async () => {
    const json = JSON.stringify(EVENT);
    expect(await collect([`data: ${json}\n`, "\n"])).toEqual([["event", EVENT]]);
  });

  it("holds the second frame back until its own separator arrives", async () => {
    const second = frame(STATUS);
    expect(await collect([frame(EVENT) + second.slice(0, 10), second.slice(10)])).toEqual([
      ["event", EVENT],
      ["status", STATUS],
    ]);
  });

  it("delivers one frame per one-byte chunk", async () => {
    const bytes = encoder.encode(frame(EVENT));
    const chunks = Array.from(bytes, (b) => new Uint8Array([b]));
    expect(await collect(chunks)).toEqual([["event", EVENT]]);
  });

  it("decodes a multi-byte UTF-8 character split across chunks", async () => {
    const payload = { ...EVENT, detail: "café — ✓" };
    const bytes = encoder.encode(frame(payload));
    const cut = bytes.indexOf(0xc3) + 1; // between the two bytes of "é"
    expect(await collect([bytes.slice(0, cut), bytes.slice(cut)])).toEqual([["event", payload]]);
  });

  it("drops a trailing incomplete frame when the stream closes", async () => {
    expect(await collect([frame(EVENT), `data: ${JSON.stringify(STATUS)}`])).toEqual([["event", EVENT]]);
  });

  it("does not recognise CRLF-terminated frames (only the bare \\n\\n separator)", async () => {
    expect(await collect([`data: ${JSON.stringify(EVENT)}\r\n\r\n`])).toEqual([]);
  });
});

describe("streamJobEvents — garbled frames", () => {
  it("skips a frame whose payload is not JSON and keeps streaming", async () => {
    expect(await collect(["data: {not json\n\n", frame(EVENT)])).toEqual([["event", EVENT]]);
  });

  it("skips a truncated JSON payload that ends at a separator", async () => {
    expect(await collect([`data: ${JSON.stringify(EVENT).slice(0, -3)}\n\n`, frame(STATUS)])).toEqual([
      ["status", STATUS],
    ]);
  });

  it("does not crash on an empty data payload", async () => {
    expect(await collect(["data:\n\n", frame(EVENT)])).toEqual([["event", EVENT]]);
  });
});

describe("streamJobEvents — failures", () => {
  it("rejects with an HttpError on a non-2xx open and keeps the token", async () => {
    setApiToken("tok");
    fetchMock.mockResolvedValueOnce(new Response("nope", { status: 500 }));
    const error = (await streamJobEvents("job-1", { onEvent: vi.fn(), onStatus: vi.fn() }).catch((e: unknown) => e)) as HttpError;
    expect(error).toBeInstanceOf(HttpError);
    expect(error.status).toBe(500);
    expect(error.issues).toEqual([{ message: "Stream failed (500)" }]);
    expect(getApiToken()).toBe("tok");
  });

  it("clears the token and rejects with an HttpError on a 401", async () => {
    setApiToken("expired");
    fetchMock.mockResolvedValueOnce(new Response("", { status: 401 }));
    const error = (await streamJobEvents("job-1", { onEvent: vi.fn(), onStatus: vi.fn() }).catch((e: unknown) => e)) as HttpError;
    expect(error).toBeInstanceOf(HttpError);
    expect(error.status).toBe(401);
    expect(error.issues).toEqual([{ message: "Stream failed (401)" }]);
    expect(getApiToken()).toBeNull();
  });

  it("rejects with a stream HttpError when a 2xx response has no body", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 200 }));
    const error = (await streamJobEvents("job-1", { onEvent: vi.fn(), onStatus: vi.fn() }).catch((e: unknown) => e)) as HttpError;
    expect(error).toBeInstanceOf(HttpError);
    expect(error.issues).toEqual([{ message: "Stream failed (200)" }]);
  });

  it("propagates a transport error raised by fetch itself", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("network down"));
    await expect(streamJobEvents("job-1", { onEvent: vi.fn(), onStatus: vi.fn() })).rejects.toThrow("network down");
  });

  it("propagates a mid-stream transport error (a chunk still queued behind it is lost)", async () => {
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode(frame(EVENT)));
        controller.error(new Error("connection reset"));
      },
    });
    fetchMock.mockResolvedValueOnce(new Response(body, { status: 200 }));
    const onEvent = vi.fn();
    await expect(streamJobEvents("job-1", { onEvent, onStatus: vi.fn() })).rejects.toThrow("connection reset");
    // controller.error() discards the queued chunk: the reader sees the error first.
    expect(onEvent.mock.calls.length).toBe(0);
  });

  it("rejects with the AbortError when the caller aborts mid-stream, and stops delivering", async () => {
    const controller = new AbortController();
    fetchMock.mockImplementationOnce((_url: string, init: RequestInit) => {
      const body = new ReadableStream<Uint8Array>({
        start(c) {
          c.enqueue(encoder.encode(frame(EVENT)));
          init.signal?.addEventListener("abort", () => c.error(new DOMException("aborted", "AbortError")));
        },
      });
      return Promise.resolve(new Response(body, { status: 200 }));
    });
    const seen: unknown[] = [];
    const promise = streamJobEvents("job-1", {
      onEvent: (e) => {
        seen.push(e);
        controller.abort();
      },
      onStatus: vi.fn(),
      signal: controller.signal,
    });
    const error = (await promise.catch((e: unknown) => e)) as DOMException;
    expect(error.name).toBe("AbortError");
    expect(seen).toEqual([EVENT]);
  });
});
