// ====== Code Summary ======
// The debounced text filter: a burst of keystrokes reaches the parent once, 350ms after the last
// one, and an unmount with a timer still armed never calls the parent.

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TextFilterInput } from "./TextFilterInput";

describe("TextFilterInput", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("reports only the last value of a burst, once the debounce elapses", () => {
    const onChange = vi.fn();
    render(<TextFilterInput value="" onChange={onChange} ariaLabel="Filter" />);
    const input = screen.getByLabelText("Filter");

    fireEvent.change(input, { target: { value: "a" } });
    vi.advanceTimersByTime(200);
    fireEvent.change(input, { target: { value: "ab" } });
    vi.advanceTimersByTime(349);
    expect(onChange).not.toHaveBeenCalled();
    expect(input).toHaveValue("ab");

    vi.advanceTimersByTime(1);
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith("ab");
  });

  it("drops a pending notification on unmount", () => {
    const onChange = vi.fn();
    const { unmount } = render(<TextFilterInput value="" onChange={onChange} ariaLabel="Filter" />);
    fireEvent.change(screen.getByLabelText("Filter"), { target: { value: "x" } });
    unmount();
    vi.advanceTimersByTime(1000);
    expect(onChange).not.toHaveBeenCalled();
  });
});
