// ====== Code Summary ======
// Render smoke-test for RootKeyConfirmGate — the action button stays disabled until the typed text
// matches exactly, and only fires onConfirm once unlocked (round-4 P4: root-key lockout guard).

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RootKeyConfirmGate } from "./RootKeyConfirmGate";

describe("RootKeyConfirmGate", () => {
  it("keeps the action disabled until the typed text matches, then confirms", () => {
    const onConfirm = vi.fn();
    render(<RootKeyConfirmGate expectedText="root" actionLabel="Confirm revoke" onConfirm={onConfirm} onCancel={vi.fn()} />);

    const button = screen.getByText("Confirm revoke");
    expect(button).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText("root"), { target: { value: "not-root" } });
    expect(button).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText("root"), { target: { value: "root" } });
    expect(button).not.toBeDisabled();

    fireEvent.click(button);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("calls onCancel when Cancel is clicked", () => {
    const onCancel = vi.fn();
    render(<RootKeyConfirmGate expectedText="root" actionLabel="Confirm rotate" onConfirm={vi.fn()} onCancel={onCancel} />);

    fireEvent.click(screen.getByText("Cancel"));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});
