// ====== Code Summary ======
// Render smoke-test for the wizard's dedicated tags editor: typing a label and pressing Enter adds
// it as a chip, and removing it (via TagsInput's own "x") drops it again.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { TagsField } from "./TagsField";

describe("TagsField — collection tags editor", () => {
  it("adds a typed tag on Enter", () => {
    const onChange = vi.fn();
    render(<TagsField values={[]} onChange={onChange} />);

    const input = screen.getByLabelText("Collection tags");
    fireEvent.change(input, { target: { value: "finance" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(onChange).toHaveBeenCalledWith(["finance"]);
  });

  it("removes an existing tag chip", () => {
    const onChange = vi.fn();
    render(<TagsField values={["finance", "q3"]} onChange={onChange} />);

    expect(screen.getByText("finance")).toBeInTheDocument();
    // Two chips, each with its own "✕" — the first one removes "finance" (list order preserved).
    fireEvent.click(screen.getAllByText("✕")[0]);

    expect(onChange).toHaveBeenCalledWith(["q3"]);
  });
});
