// ====== Code Summary ======
// Characterization (safety net) of api/http.ts: records TODAY's behaviour of the fetch chokepoint so
// the planned api split (R-31) cannot change it silently. Pins every `detail` shape `normalizeDetail`
// understands (through `apiFetch`, it is not exported), the 204 / 401 / Retry-After / non-JSON paths,
// the Bearer attachment and the Blob variant. A diff here is a behaviour change to review, not a
// test to "fix".

// ====== Third-Party Library Imports ======
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// ====== Local Project Imports ======
import {
  API_TOKEN_CLEARED_EVENT,
  apiFetch,
  apiFetchBlob,
  clearApiToken,
  getApiToken,
  HttpError,
  jsonInit,
  setApiToken,
} from "./http";

const fetchMock = vi.fn();

beforeEach(() => {
  localStorage.clear();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown, status: number, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });
}

/** Runs apiFetch against one error response and returns the HttpError it throws. */
async function errorOf(response: Response): Promise<HttpError> {
  fetchMock.mockResolvedValueOnce(response);
  const error = await apiFetch("/x").catch((e: unknown) => e);
  expect(error).toBeInstanceOf(HttpError);
  return error as HttpError;
}

describe("api token store", () => {
  it("reads null when no token is stored", () => {
    expect(getApiToken()).toBeNull();
  });

  it("persists and reads back the token", () => {
    setApiToken("tok");
    expect(getApiToken()).toBe("tok");
    expect(localStorage.getItem("docforge_api_token")).toBe("tok");
  });

  it("clears the token and fires the cleared event on window", () => {
    setApiToken("tok");
    const listener = vi.fn();
    window.addEventListener(API_TOKEN_CLEARED_EVENT, listener);
    clearApiToken();
    window.removeEventListener(API_TOKEN_CLEARED_EVENT, listener);
    expect(getApiToken()).toBeNull();
    expect(listener).toHaveBeenCalledTimes(1);
    expect(API_TOKEN_CLEARED_EVENT).toBe("docforge:api-token-cleared");
  });
});

describe("jsonInit", () => {
  it("builds a JSON request init", () => {
    expect(jsonInit("POST", { a: 1 })).toEqual({
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: '{"a":1}',
    });
  });
});

describe("apiFetch — success paths", () => {
  it("returns the parsed JSON body of a 2xx", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ ok: true }, 200));
    await expect(apiFetch("/x")).resolves.toEqual({ ok: true });
  });

  it("returns undefined for a 204 without reading a body", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await expect(apiFetch("/x")).resolves.toBeUndefined();
  });

  it("passes the url and init through, with headers untouched, when no token is stored", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({}, 200));
    await apiFetch("/x", { method: "PUT", headers: { "X-A": "1" } });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/x");
    expect(init).toEqual({ method: "PUT", headers: { "X-A": "1" } });
  });

  it("leaves headers undefined when there is neither a token nor an init", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({}, 200));
    await apiFetch("/x");
    expect(fetchMock.mock.calls[0][1].headers).toBeUndefined();
  });

  it("attaches the Bearer header when a token is stored", async () => {
    setApiToken("tok");
    fetchMock.mockResolvedValueOnce(jsonResponse({}, 200));
    await apiFetch("/x");
    expect(fetchMock.mock.calls[0][1].headers).toEqual({ Authorization: "Bearer tok" });
  });

  it("merges the Bearer header over the caller's own plain-object headers", async () => {
    setApiToken("tok");
    fetchMock.mockResolvedValueOnce(jsonResponse({}, 200));
    await apiFetch("/x", { ...jsonInit("POST", {}) });
    expect(fetchMock.mock.calls[0][1].headers).toEqual({
      "Content-Type": "application/json",
      Authorization: "Bearer tok",
    });
  });

  it("lets the stored token win over a caller-supplied Authorization header", async () => {
    setApiToken("tok");
    fetchMock.mockResolvedValueOnce(jsonResponse({}, 200));
    await apiFetch("/x", { headers: { Authorization: "Bearer other" } });
    expect(fetchMock.mock.calls[0][1].headers).toEqual({ Authorization: "Bearer tok" });
  });
});

describe("apiFetch — error `detail` shapes (normalizeDetail)", () => {
  it("a plain string detail becomes one message-only issue", async () => {
    const error = await errorOf(jsonResponse({ detail: "Collection not found" }, 404));
    expect(error.status).toBe(404);
    expect(error.issues).toEqual([{ message: "Collection not found" }]);
    expect(error.message).toBe("Collection not found");
    expect(error.detail).toBeNull();
    expect(error.retryAfterSeconds).toBeNull();
  });

  it("a pydantic ValidationError string detail is humanized into one issue per field", async () => {
    const raw =
      "1 validation error for QueryNormalizeConfig\ncandidate_multiplier\n  Input should be greater than 0 [type=greater_than, input_value=-5, input_type=int]\n    For further information visit https://errors.pydantic.dev/2.13/v/greater_than";
    const error = await errorOf(jsonResponse({ detail: raw }, 422));
    expect(error.issues).toEqual([{ location: "candidate_multiplier", message: "Input should be greater than 0" }]);
  });

  it("an array of strings becomes one message-only issue each, joined with '; ' in the message", async () => {
    const error = await errorOf(jsonResponse({ detail: ["first", "second"] }, 400));
    expect(error.issues).toEqual([{ message: "first" }, { message: "second" }]);
    expect(error.message).toBe("first; second");
    expect(error.detail).toBeNull();
  });

  it("the collections router's {code, location, message} entries keep all three fields", async () => {
    const error = await errorOf(
      jsonResponse({ detail: [{ code: "bad_field", location: "fields.0", message: "nope" }, { message: "bare" }] }, 422),
    );
    expect(error.issues).toEqual([
      { code: "bad_field", location: "fields.0", message: "nope" },
      { code: undefined, location: undefined, message: "bare" },
    ]);
  });

  it("the search router's {code, detail} entry keeps the code and reads detail as the message", async () => {
    const error = await errorOf(jsonResponse({ detail: [{ code: "embedder_unreachable", detail: "embedder down" }] }, 502));
    expect(error.issues).toEqual([{ code: "embedder_unreachable", message: "embedder down" }]);
  });

  it("FastAPI's {loc, msg, type} entries map to location (dot-joined), message and code", async () => {
    const error = await errorOf(
      jsonResponse({ detail: [{ loc: ["body", "fields", 0, "name"], msg: "field required", type: "missing" }] }, 422),
    );
    expect(error.issues).toEqual([{ code: "missing", location: "body.fields.0.name", message: "field required" }]);
  });

  it("a FastAPI entry without loc/type leaves location and code undefined", async () => {
    const error = await errorOf(jsonResponse({ detail: [{ msg: "just msg" }] }, 422));
    expect(error.issues).toEqual([{ code: undefined, location: undefined, message: "just msg" }]);
  });

  it("an entry of unknown shape is stringified as JSON", async () => {
    const error = await errorOf(jsonResponse({ detail: [{ weird: 1 }] }, 422));
    expect(error.issues).toEqual([{ message: '{"weird":1}' }]);
  });

  it("an object detail is normalized as a one-entry list and kept raw in `detail`", async () => {
    const raw = { code: "estimate_required", message: "Run an estimate first", cost_usd: 1.5 };
    const error = await errorOf(jsonResponse({ detail: raw }, 409));
    expect(error.issues).toEqual([{ code: "estimate_required", location: undefined, message: "Run an estimate first" }]);
    expect(error.detail).toEqual(raw);
  });

  it("an object detail with only {code, detail} keeps the code and is kept raw", async () => {
    const raw = { code: "replay_unsupported", detail: "cannot replay" };
    const error = await errorOf(jsonResponse({ detail: raw }, 409));
    expect(error.issues).toEqual([{ code: "replay_unsupported", message: "cannot replay" }]);
    expect(error.detail).toEqual(raw);
  });

  it("a body without a `detail` key is itself treated as the detail", async () => {
    const error = await errorOf(jsonResponse({ message: "boom" }, 500));
    expect(error.issues).toEqual([{ code: undefined, location: undefined, message: "boom" }]);
    expect(error.detail).toEqual({ message: "boom" });
  });

  it("a top-level array body is normalized like an array detail and leaves `detail` null", async () => {
    const error = await errorOf(jsonResponse(["a"], 400));
    expect(error.issues).toEqual([{ message: "a" }]);
    expect(error.detail).toBeNull();
  });

  it("a null `detail` falls back to the whole body, stringified", async () => {
    const error = await errorOf(jsonResponse({ detail: null }, 500));
    expect(error.issues).toEqual([{ message: '{"detail":null}' }]);
    expect(error.detail).toEqual({ detail: null });
  });

  it("an empty detail list falls back to the generic issue", async () => {
    const error = await errorOf(jsonResponse({ detail: [] }, 422));
    expect(error.issues).toEqual([{ message: "Request failed (422)" }]);
    expect(error.detail).toBeNull();
  });

  it("a numeric detail (neither string, array nor object) falls back to the generic issue", async () => {
    const error = await errorOf(jsonResponse({ detail: 42 }, 500));
    expect(error.issues).toEqual([{ message: "Request failed (500)" }]);
  });

  it("a non-JSON body keeps the generic issue and a null detail", async () => {
    const error = await errorOf(new Response("<html>Bad gateway</html>", { status: 502 }));
    expect(error.status).toBe(502);
    expect(error.issues).toEqual([{ message: "Request failed (502)" }]);
    expect(error.message).toBe("Request failed (502)");
    expect(error.detail).toBeNull();
  });
});

describe("apiFetch — Retry-After", () => {
  it.each([
    ["30", 30],
    ["1.5", 1.5],
    ["0", null],
    ["-3", null],
    ["soon", null],
    ["Wed, 21 Oct 2026 07:28:00 GMT", null],
  ])("parses Retry-After %j as %j", async (header, expected) => {
    const error = await errorOf(jsonResponse({ detail: "slow down" }, 429, { "Retry-After": header }));
    expect(error.status).toBe(429);
    expect(error.retryAfterSeconds).toBe(expected);
  });

  it("is null when the header is absent", async () => {
    const error = await errorOf(jsonResponse({ detail: "slow down" }, 429));
    expect(error.retryAfterSeconds).toBeNull();
  });

  it("is parsed even when the body is not JSON", async () => {
    const error = await errorOf(new Response("busy", { status: 503, headers: { "Retry-After": "7" } }));
    expect(error.retryAfterSeconds).toBe(7);
    expect(error.issues).toEqual([{ message: "Request failed (503)" }]);
  });
});

describe("apiFetch — 401 handling", () => {
  it("clears the stored token, fires the cleared event and still throws the HttpError", async () => {
    setApiToken("expired");
    const listener = vi.fn();
    window.addEventListener(API_TOKEN_CLEARED_EVENT, listener);
    const error = await errorOf(jsonResponse({ detail: "Invalid token" }, 401));
    window.removeEventListener(API_TOKEN_CLEARED_EVENT, listener);
    expect(error.status).toBe(401);
    expect(error.issues).toEqual([{ message: "Invalid token" }]);
    expect(getApiToken()).toBeNull();
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it.each([403, 404, 500])("keeps the token on a %i", async (status) => {
    setApiToken("tok");
    await errorOf(jsonResponse({ detail: "x" }, status));
    expect(getApiToken()).toBe("tok");
  });
});

describe("apiFetchBlob", () => {
  it("returns the response Blob and sends no headers without a token", async () => {
    fetchMock.mockResolvedValueOnce(new Response("bytes", { status: 200 }));
    const blob = await apiFetchBlob("/img");
    expect(await blob.text()).toBe("bytes");
    expect(fetchMock).toHaveBeenCalledWith("/img", { headers: undefined });
  });

  it("attaches the Bearer header when a token is stored", async () => {
    setApiToken("tok");
    fetchMock.mockResolvedValueOnce(new Response("bytes", { status: 200 }));
    await apiFetchBlob("/img");
    expect(fetchMock).toHaveBeenCalledWith("/img", { headers: { Authorization: "Bearer tok" } });
  });

  it("throws a generic HttpError on non-2xx, ignoring the body and Retry-After", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "ignored" }, 404, { "Retry-After": "5" }));
    const error = (await apiFetchBlob("/img").catch((e: unknown) => e)) as HttpError;
    expect(error).toBeInstanceOf(HttpError);
    expect(error.status).toBe(404);
    expect(error.issues).toEqual([{ message: "Request failed (404)" }]);
    expect(error.detail).toBeNull();
    expect(error.retryAfterSeconds).toBeNull();
  });

  it("clears the token and fires the cleared event on a 401", async () => {
    setApiToken("expired");
    const listener = vi.fn();
    window.addEventListener(API_TOKEN_CLEARED_EVENT, listener);
    fetchMock.mockResolvedValueOnce(new Response("", { status: 401 }));
    const error = (await apiFetchBlob("/img").catch((e: unknown) => e)) as HttpError;
    window.removeEventListener(API_TOKEN_CLEARED_EVENT, listener);
    expect(error.status).toBe(401);
    expect(getApiToken()).toBeNull();
    expect(listener).toHaveBeenCalledTimes(1);
  });

  it("keeps the token on a non-401 error", async () => {
    setApiToken("tok");
    fetchMock.mockResolvedValueOnce(new Response("", { status: 500 }));
    await apiFetchBlob("/img").catch(() => undefined);
    expect(getApiToken()).toBe("tok");
  });
});

describe("HttpError", () => {
  it("falls back to a generic message when there are no issues", () => {
    const error = new HttpError(500, []);
    expect(error.message).toBe("Request failed (500)");
    expect(error.detail).toBeNull();
    expect(error.retryAfterSeconds).toBeNull();
  });
});
