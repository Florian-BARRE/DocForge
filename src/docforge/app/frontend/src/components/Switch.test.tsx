// ====== Code Summary ======
// Regression test for round-4 T1: `Switch` (role="switch", used by every non-stage boolean toggle)
// must render its ON state in forge accent — matching `StageSwitch`'s ON state byte-for-byte — not
// the steel `theme.color.dim` a prior audit had moved it to. A locked switch stays steel + padlock,
// deliberately distinct from a plain "on".

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { theme } from "../theme";
import { Switch } from "./Switch";

function trackOf(container: HTMLElement): HTMLElement {
  return container.querySelector("button")!;
}

describe("Switch — ON reads forge accent, matching StageSwitch", () => {
  it("checked renders the accent fill, not steel", () => {
    const { container } = render(<Switch checked onChange={() => {}} />);
    const track = trackOf(container);
    expect(track.style.background).toContain(theme.color.accent);
    expect(track.style.background).not.toContain(theme.color.dim);
  });

  it("unchecked renders the neutral empty track", () => {
    const { container } = render(<Switch checked={false} onChange={() => {}} />);
    expect(trackOf(container).style.background).toContain(theme.color.line);
  });

  it("locked stays steel (distinct from a plain on), regardless of checked", () => {
    const { container } = render(<Switch checked locked onChange={() => {}} />);
    const track = trackOf(container);
    expect(track.style.background).toContain(theme.color.dim);
    expect(track.style.background).not.toContain(theme.color.accent);
  });

  it("renders with no throw across every state (render smoke)", () => {
    for (const checked of [true, false]) {
      for (const disabled of [true, false]) {
        const { unmount } = render(<Switch checked={checked} disabled={disabled} onChange={() => {}} />);
        unmount();
      }
    }
  });
});
