// ====== Code Summary ======
// The one navigation channel of the shell: `NavigateProvider` holds the single `Navigate` function
// (App.tsx's `setView`) and `useNavigate()` hands that same function to any component below it, so
// a deep component calls `navigate({ name: "job", ... })` instead of receiving a navigate
// callback prop through every intermediate layer. Routing itself (view state, URL sync, the route table in
// `routes.tsx`) is unchanged — this only replaces HOW a component reaches the navigate function.

// ====== Third-Party Library Imports ======
import { createContext, useContext, type ReactNode } from "react";

// ====== Local Project Imports ======
import type { Navigate } from "./view";

const NavigateContext = createContext<Navigate | null>(null);

interface NavigateProviderProps {
  /** The shell's navigate function — the same one the route table hands to the routed entry pages. */
  navigate: Navigate;
  children: ReactNode;
}

/** Provide `navigate` to every component below; mounted once, at the root of App. */
export function NavigateProvider({ navigate, children }: NavigateProviderProps) {
  return <NavigateContext.Provider value={navigate}>{children}</NavigateContext.Provider>;
}

/**
 * The typed navigate function of the shell.
 *
 * @returns A stable `(view: View) => void` — the target is a `View`, so a mistyped route name or
 *          a missing/extra param is a compile error.
 * @throws Error when called outside a `NavigateProvider` (fail fast: a page without a router
 *         would silently never navigate).
 */
export function useNavigate(): Navigate {
  const navigate = useContext(NavigateContext);
  if (navigate === null) throw new Error("useNavigate() must be called inside a <NavigateProvider>");
  return navigate;
}
