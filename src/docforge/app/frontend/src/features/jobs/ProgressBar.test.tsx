// ====== Code Summary ======
// Regression test for iteration-3 FIX-C: a terminal job's progress bar must never read as forge
// accent (the ONE "active work" signal, per brand.md) — `failed` gets the error ink, `cancelled`
// gets a hatched skip fill (a deliberate stop, not a solid "still filling" bar), and only a
// still-running/pending job legitimately gets the accent fill.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { theme } from "../../theme";
import { ProgressBar } from "./ProgressBar";

function fillOf(container: HTMLElement): HTMLElement {
  return container.firstChild!.firstChild as HTMLElement;
}

describe("ProgressBar — terminal statuses never render the forge accent", () => {
  it("failed uses the error ink, not accent", () => {
    const { container } = render(<ProgressBar progress={40} status="failed" />);
    const fill = fillOf(container);
    expect(fill.style.background).toContain(theme.color.error);
    expect(fill.style.background).not.toContain(theme.color.accent);
  });

  it("cancelled uses a hatched skip fill, not a solid accent bar", () => {
    const { container } = render(<ProgressBar progress={40} status="cancelled" />);
    const fill = fillOf(container);
    expect(fill.style.background).toContain("repeating-linear-gradient");
    expect(fill.style.background).toContain(theme.color.skip);
    expect(fill.style.background).not.toContain(theme.color.accent);
  });

  it("done uses the ok ink", () => {
    const { container } = render(<ProgressBar progress={100} status="done" />);
    expect(fillOf(container).style.background).toContain(theme.color.ok);
  });

  it("a still-running job legitimately gets the forge accent (the one active thing)", () => {
    const { container } = render(<ProgressBar progress={40} status="running" />);
    expect(fillOf(container).style.background).toContain(theme.color.accent);
  });

  it("renders with no throw across every status (render smoke)", () => {
    for (const status of ["pending", "running", "done", "failed", "cancelled"] as const) {
      const { unmount } = render(<ProgressBar progress={50} status={status} />);
      expect(screen).toBeTruthy();
      unmount();
    }
  });
});
