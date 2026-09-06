// ====== Code Summary ======
// Render smoke-test for the fleet card's tag chips: renders nothing for an untagged collection,
// shows every tag up to the cap, and collapses the rest into a "+N" overflow pill.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CollectionTagChips } from "./CollectionTagChips";

describe("CollectionTagChips", () => {
  it("renders nothing when untagged", () => {
    const { container } = render(<CollectionTagChips tags={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows every tag chip within the cap", () => {
    render(<CollectionTagChips tags={["finance", "q3"]} />);
    expect(screen.getByText("finance")).toBeInTheDocument();
    expect(screen.getByText("q3")).toBeInTheDocument();
  });

  it("collapses tags beyond the cap into a +N overflow pill", () => {
    render(<CollectionTagChips tags={["a", "b", "c", "d", "e"]} />);
    expect(screen.getByText("a")).toBeInTheDocument();
    expect(screen.getByText("b")).toBeInTheDocument();
    expect(screen.getByText("c")).toBeInTheDocument();
    expect(screen.getByText("+2")).toBeInTheDocument();
    expect(screen.queryByText("d")).not.toBeInTheDocument();
  });
});
