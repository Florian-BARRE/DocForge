// ====== Code Summary ======
// Render smoke-test for the chip-multiselect: picking a suggestion chip adds it, clicking it again
// removes it, and the zero-formats state shows the required inline message (never silently lets
// the step "look" satisfiable with no chips selected).

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { FormatsField } from "./FormatsField";

describe("FormatsField — chip-multiselect", () => {
  it("shows the required message and no formats when empty", () => {
    render(<FormatsField values={[]} onChange={vi.fn()} />);

    expect(screen.getByText("Add at least one accepted format to continue.")).toBeInTheDocument();
  });

  it("adds a suggested format on click and removes it again on a second click", () => {
    const onChange = vi.fn();
    // The suggestion chip is a `<button aria-pressed>` — scoped by role so it never collides with
    // the separately-rendered "selected" chip inside TagsInput once "pdf" is picked.
    const { rerender } = render(<FormatsField values={[]} onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: "pdf" }));
    expect(onChange).toHaveBeenCalledWith(["pdf"]);

    rerender(<FormatsField values={["pdf"]} onChange={onChange} />);
    expect(screen.queryByText("Add at least one accepted format to continue.")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "pdf" }));
    expect(onChange).toHaveBeenLastCalledWith([]);
  });
});
