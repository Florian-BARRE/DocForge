// ====== Code Summary ======
// Render smoke-test for TracePayloadView: a blob-hash field renders as a clickable
// view/download reference (never an opaque string), a long/multi-line text field renders
// readably (not an escaped JSON one-liner), the "Raw JSON" toggle swaps to the untouched dump
// and back, and odd/empty payload shapes (null, {}, a bytes-placeholder string) never throw.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TracePayloadView } from "./TracePayloadView";

const SOURCE_HASH = "a".repeat(64);

describe("TracePayloadView", () => {
  it("renders a blob-hash field as a clickable view/download reference", () => {
    render(<TracePayloadView payload={{ source_hash: SOURCE_HASH, title: "Doc" }} />);

    const ref = screen.getByRole("button", { name: /view\/download/ });
    expect(ref).toBeInTheDocument();
    expect(ref.textContent).toContain(SOURCE_HASH.slice(0, 12));
    // Never shown as an opaque raw string sitting next to its label.
    expect(screen.queryByText(SOURCE_HASH)).not.toBeInTheDocument();
  });

  it("detects a bare 64-hex string as a blob reference even under an unrelated key name", () => {
    render(<TracePayloadView payload={{ some_field: SOURCE_HASH }} />);
    expect(screen.getByRole("button", { name: /view\/download/ })).toBeInTheDocument();
  });

  it("renders a long multi-line text field readably, not as an escaped one-liner", () => {
    const text = "First line of chunk text.\nSecond line, well past the inline threshold for sure.";
    render(<TracePayloadView payload={{ text }} />);

    // The real newline survives (textContent collapses it, but no literal backslash-n appears).
    expect(screen.getByText((_, node) => node?.textContent === text)).toBeInTheDocument();
    expect(screen.queryByText(/\\n/)).not.toBeInTheDocument();
  });

  it("keeps a bytes-placeholder string dim/plain, not treated as a blob reference", () => {
    render(<TracePayloadView payload={{ crop: "<12345 bytes>" }} />);
    expect(screen.getByText("<12345 bytes>")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /view\/download/ })).not.toBeInTheDocument();
  });

  it("toggles between formatted and raw JSON view", () => {
    render(<TracePayloadView payload={{ blocks: 3 }} />);

    expect(screen.getByText("blocks:")).toBeInTheDocument();
    expect(screen.queryByText(/"blocks": 3/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Raw JSON" }));
    expect(screen.getByText(/"blocks": 3/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Formatted view" }));
    expect(screen.getByText("blocks:")).toBeInTheDocument();
  });

  it("never throws on odd/empty payload shapes", () => {
    expect(() => render(<TracePayloadView payload={null} />)).not.toThrow();
    expect(() => render(<TracePayloadView payload={{}} />)).not.toThrow();
    expect(() => render(<TracePayloadView payload={[]} />)).not.toThrow();
    expect(() => render(<TracePayloadView payload={"plain string"} />)).not.toThrow();
    expect(() => render(<TracePayloadView payload={{ nested: { a: [1, 2, { b: null }] } }} />)).not.toThrow();
  });
});
