// ====== Code Summary ======
// Render smoke-test for Breadcrumb — every non-last segment with a `view` is a clickable link that
// calls `onNavigate` with that segment's view; the last segment is plain (never a link) and carries
// `aria-current="page"` regardless of whether it has a `view`; a mid-trail segment with no `view`
// (e.g. "Admin", a sidebar section with no page of its own) renders as plain text too.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Breadcrumb, type BreadcrumbItem } from "./Breadcrumb";

const items: BreadcrumbItem[] = [
  { label: "Collections", view: { name: "collections" } },
  { label: "Acme Corp", view: { name: "collection", collectionId: "col-1" } },
  { label: "report.pdf" },
];

describe("Breadcrumb", () => {
  it("renders every segment", () => {
    render(<Breadcrumb items={items} onNavigate={vi.fn()} />);
    expect(screen.getByText("Collections")).toBeInTheDocument();
    expect(screen.getByText("Acme Corp")).toBeInTheDocument();
    expect(screen.getByText("report.pdf")).toBeInTheDocument();
  });

  it("navigates to a non-last segment's view when clicked", () => {
    const onNavigate = vi.fn();
    render(<Breadcrumb items={items} onNavigate={onNavigate} />);
    fireEvent.click(screen.getByText("Acme Corp"));
    expect(onNavigate).toHaveBeenCalledWith({ name: "collection", collectionId: "col-1" });
  });

  it("marks the last segment as the current page and never a link", () => {
    render(<Breadcrumb items={items} onNavigate={vi.fn()} />);
    const last = screen.getByText("report.pdf");
    expect(last).toHaveAttribute("aria-current", "page");
    expect(last.tagName).not.toBe("BUTTON");
  });

  it("renders a mid-trail segment with no view as plain text, not a link", () => {
    render(
      <Breadcrumb
        items={[{ label: "Admin" }, { label: "API Keys", view: { name: "api-keys" } }, { label: "prod-key" }]}
        onNavigate={vi.fn()}
      />,
    );
    expect(screen.getByText("Admin").tagName).not.toBe("BUTTON");
  });

  it("exposes the nav landmark", () => {
    render(<Breadcrumb items={items} onNavigate={vi.fn()} />);
    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toBeInTheDocument();
  });
});
