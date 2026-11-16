// ====== Code Summary ======
// Unit test of the shell's navigation channel: `useNavigate()` returns exactly the function the
// `NavigateProvider` holds (one navigation path), a deep component can call it with a typed View,
// and using the hook outside a provider fails fast instead of silently never navigating.

// ====== Third-Party Library Imports ======
import { fireEvent, render, renderHook, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// ====== Local Project Imports ======
import { NavigateProvider, useNavigate } from "./navigation";

function GoToFleet() {
  const navigate = useNavigate();
  return <button type="button" onClick={() => navigate({ name: "fleet" })}>go</button>;
}

describe("useNavigate", () => {
  it("returns the very function the provider holds", () => {
    const navigate = vi.fn();
    const { result } = renderHook(() => useNavigate(), {
      wrapper: ({ children }) => <NavigateProvider navigate={navigate}>{children}</NavigateProvider>,
    });
    expect(result.current).toBe(navigate);
  });

  it("lets a deeply nested component navigate without receiving a prop", () => {
    const navigate = vi.fn();
    render(
      <NavigateProvider navigate={navigate}>
        <div><section><GoToFleet /></section></div>
      </NavigateProvider>,
    );
    fireEvent.click(screen.getByText("go"));
    expect(navigate).toHaveBeenCalledExactlyOnceWith({ name: "fleet" });
  });

  it("throws outside a NavigateProvider", () => {
    const quiet = vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => renderHook(() => useNavigate())).toThrow(/NavigateProvider/);
    quiet.mockRestore();
  });
});
