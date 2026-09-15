// ====== Code Summary ======
// Guards the row breakpoint that fixes the "chunk column squished sideways" bug: below the
// threshold the row must stack; at/above it, and while unmeasured (0/negative), it must stay
// side-by-side (the safe default that matches today's layout until the ResizeObserver reports in).

import { describe, expect, it } from "vitest";
import { ROW_STACK_BREAKPOINT_PX, shouldStackColumns } from "./layoutBreakpoint";

describe("shouldStackColumns", () => {
  it("stacks below the breakpoint", () => {
    expect(shouldStackColumns(ROW_STACK_BREAKPOINT_PX - 1)).toBe(true);
    expect(shouldStackColumns(800)).toBe(true);
  });

  it("stays side-by-side at/above the breakpoint", () => {
    expect(shouldStackColumns(ROW_STACK_BREAKPOINT_PX)).toBe(false);
    expect(shouldStackColumns(1600)).toBe(false);
  });

  it("stays side-by-side when unmeasured (0 or negative)", () => {
    expect(shouldStackColumns(0)).toBe(false);
    expect(shouldStackColumns(-1)).toBe(false);
  });
});
