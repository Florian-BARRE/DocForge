// ====== Code Summary ======
// Render smoke-test for DateInput — renders with its accessible name, respects a controlled ISO
// value, and emits the raw ISO string on change (the same value contract as the native
// `<input type="date">` it replaces).

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DateInput } from "./DateInput";

describe("DateInput", () => {
  it("renders with its accessible name and controlled value", () => {
    render(<DateInput value="2026-01-15" onChange={vi.fn()} ariaLabel="created from" />);
    const input = screen.getByLabelText("created from") as HTMLInputElement;
    expect(input).toBeInTheDocument();
    expect(input.value).toBe("2026-01-15");
    expect(input.type).toBe("date");
  });

  it("emits the raw ISO date string on change", () => {
    const onChange = vi.fn();
    render(<DateInput value="" onChange={onChange} ariaLabel="created to" />);
    fireEvent.change(screen.getByLabelText("created to"), { target: { value: "2026-02-20" } });
    expect(onChange).toHaveBeenCalledWith("2026-02-20");
  });
});
