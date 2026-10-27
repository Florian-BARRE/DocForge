// ====== Code Summary ======
// Regression test for round-4 T7: the Off/Rewrite/HyDE segmented pill must use the SAME
// active-choice language as every other segmented control in the app (accent background on the
// selected option) — including "Off", not just the two options that fire a paid LLM call.

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Palette } from "../../api/types";
import { theme } from "../../theme";
import { SearchQueryCard } from "./SearchQueryCard";

const palette: Palette = { families: [] };

describe("SearchQueryCard — active segment is always accent", () => {
  it("paints the selected 'Off' option with the accent background, like Rewrite/HyDE would", () => {
    render(
      <SearchQueryCard
        active={null}
        config={null}
        palette={palette}
        onSelect={vi.fn()}
        onChangeConfig={vi.fn()}
      />,
    );
    const off = screen.getByRole("radio", { name: "Off" });
    expect(off).toHaveAttribute("aria-checked", "true");
    // jsdom's toHaveStyle does not match the background shorthand: read the inline style.
    expect(off.style.background).toBe(theme.color.accent);
    expect(off).toHaveStyle({ color: theme.color.onAccent });

    const rewrite = screen.getByRole("radio", { name: "Rewrite" });
    expect(rewrite).toHaveAttribute("aria-checked", "false");
    expect(rewrite.style.background).toBe("transparent");
  });

  it("paints the selected 'Rewrite' option with the same accent background", () => {
    render(
      <SearchQueryCard
        active="rewrite"
        config={{}}
        palette={palette}
        onSelect={vi.fn()}
        onChangeConfig={vi.fn()}
      />,
    );
    const rewrite = screen.getByRole("radio", { name: "Rewrite" });
    expect(rewrite).toHaveAttribute("aria-checked", "true");
    expect(rewrite.style.background).toBe(theme.color.accent);
    expect(rewrite).toHaveStyle({ color: theme.color.onAccent });
  });
});
