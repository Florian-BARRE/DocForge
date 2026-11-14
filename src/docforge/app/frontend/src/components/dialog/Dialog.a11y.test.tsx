// ====== Code Summary ======
// Accessibility contract of the shared dialog shell (`Dialog`, `ConfirmDialog`) that every modal of
// the app renders through: role/aria-modal and labelling, Escape and backdrop close, focus moved in,
// trapped and restored, the "×" button disabled while pending, and the body scroll lock.

import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { ConfirmDialog } from "./ConfirmDialog";
import { Dialog } from "./Dialog";

const press = (key: string, init: KeyboardEventInit = {}) =>
  fireEvent.keyDown(document.activeElement ?? document.body, { key, ...init });

function Host({ onClose = () => {} }: { onClose?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>open</button>
      {open && (
        <Dialog title="Hello" onClose={() => { onClose(); setOpen(false); }}>
          <button>first</button>
          <button>last</button>
        </Dialog>
      )}
    </>
  );
}

describe("Dialog — semantics", () => {
  it("is a modal dialog labelled by its title", () => {
    render(<Dialog title="Hello" onClose={() => {}}>body</Dialog>);
    const dialog = screen.getByRole("dialog", { name: "Hello" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAttribute("aria-labelledby", screen.getByRole("heading", { name: "Hello" }).id);
  });

  it("can be labelled by ariaLabel or an external heading id", () => {
    const { unmount } = render(<Dialog ariaLabel="Custom" onClose={() => {}}>x</Dialog>);
    expect(screen.getByRole("dialog", { name: "Custom" })).toBeInTheDocument();
    unmount();
    render(<Dialog labelledBy="h" onClose={() => {}}><h2 id="h">Outer</h2></Dialog>);
    expect(screen.getByRole("dialog", { name: "Outer" })).toBeInTheDocument();
  });

  it("portals to document.body by default and renders in-tree with portal={false}", () => {
    const { container, unmount } = render(<Dialog title="T" onClose={() => {}}>x</Dialog>);
    expect(container.querySelector('[role="dialog"]')).toBeNull();
    expect(document.body.querySelector('[role="dialog"]')).not.toBeNull();
    unmount();
    const inTree = render(<Dialog title="T" portal={false} onClose={() => {}}>x</Dialog>);
    expect(inTree.container.querySelector('[role="dialog"]')).not.toBeNull();
  });
});

describe("Dialog — closing", () => {
  it("closes on Escape", () => {
    const onClose = vi.fn();
    render(<Dialog title="T" onClose={onClose}>x</Dialog>);
    press("Escape");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes on a backdrop click but not on a click inside the panel", () => {
    const onClose = vi.fn();
    render(<Dialog title="T" onClose={onClose}>inside</Dialog>);
    const dialog = screen.getByRole("dialog");
    fireEvent.click(dialog);
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(dialog.parentElement!);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("ignores backdrop clicks when closeOnBackdrop is false", () => {
    const onClose = vi.fn();
    render(<Dialog title="T" closeOnBackdrop={false} onClose={onClose}>x</Dialog>);
    fireEvent.click(screen.getByRole("dialog").parentElement!);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("renders a Close button only on request, disabled while closeDisabled", () => {
    const { unmount } = render(<Dialog title="T" onClose={() => {}}>x</Dialog>);
    expect(screen.queryByRole("button", { name: "Close" })).toBeNull();
    unmount();
    const onClose = vi.fn();
    const { rerender } = render(<Dialog title="T" showClose onClose={onClose}>x</Dialog>);
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    rerender(<Dialog title="T" showClose closeDisabled onClose={onClose}>x</Dialog>);
    expect(screen.getByRole("button", { name: "Close" })).toBeDisabled();
  });
});

describe("Dialog — focus", () => {
  it("moves focus in, wraps Tab/Shift-Tab at the edges, and restores focus to the opener on close", () => {
    render(<Host />);
    const opener = screen.getByRole("button", { name: "open" });
    opener.focus();
    fireEvent.click(opener);
    const first = screen.getByRole("button", { name: "first" });
    const last = screen.getByRole("button", { name: "last" });
    expect(first).toHaveFocus();
    press("Tab", { shiftKey: true });
    expect(last).toHaveFocus();
    press("Tab");
    expect(first).toHaveFocus();
    press("Escape");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(opener).toHaveFocus();
  });
});

describe("Dialog — body scroll lock", () => {
  it("locks body scroll while mounted, restores it after, and survives stacked dialogs", () => {
    document.body.style.overflow = "auto";
    const a = render(<Dialog title="A" onClose={() => {}}>x</Dialog>);
    expect(document.body.style.overflow).toBe("hidden");
    const b = render(<Dialog title="B" onClose={() => {}}>x</Dialog>);
    a.unmount();
    expect(document.body.style.overflow).toBe("hidden");
    b.unmount();
    expect(document.body.style.overflow).toBe("auto");
    document.body.style.overflow = "";
  });
});

describe("ConfirmDialog", () => {
  const base = { title: "Sure?", confirmLabel: "Do it", pendingLabel: "doing…" };

  it("confirms and cancels", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(<ConfirmDialog {...base} onConfirm={onConfirm} onCancel={onCancel}>body</ConfirmDialog>);
    fireEvent.click(screen.getByRole("button", { name: "Do it" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("disables Cancel, confirm and the Close button while pending, and shows the pending label", () => {
    render(<ConfirmDialog {...base} showClose pending onConfirm={() => {}} onCancel={() => {}}>body</ConfirmDialog>);
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "doing…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Close" })).toBeDisabled();
  });

  it("keeps confirm disabled on confirmDisabled and shows the error", () => {
    render(<ConfirmDialog {...base} confirmDisabled error="boom" onConfirm={() => {}} onCancel={() => {}}>body</ConfirmDialog>);
    expect(screen.getByRole("button", { name: "Do it" })).toBeDisabled();
    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("routes Escape and the backdrop to onCancel", () => {
    const onCancel = vi.fn();
    render(<ConfirmDialog {...base} onConfirm={() => {}} onCancel={onCancel}>body</ConfirmDialog>);
    press("Escape");
    fireEvent.click(screen.getByRole("dialog").parentElement!);
    expect(onCancel).toHaveBeenCalledTimes(2);
  });
});
