// ====== Code Summary ======
// Unit test of the typed route table: it declares one renderer per View variant, and every routed
// entry page receives, as `onNavigate`, the very function `useNavigate()` returns below the
// provider (single source of truth, no second navigation path). Pages are inert stubs.

// ====== Third-Party Library Imports ======
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// ====== Local Project Imports ======
import { ROUTES, renderRoute } from "./routes";
import { NavigateProvider } from "./shell/navigation";
import type { Navigate, View } from "./shell/view";

const probe = vi.hoisted(() => ({ seen: [] as Array<{ page: string; prop: unknown; hook: unknown }> }));

vi.mock("./features/home/HomePage", async () => {
  const { useNavigate: hook } = await import("./shell/navigation");
  return {
    HomePage: ({ onNavigate }: { onNavigate: unknown }) => {
      probe.seen.push({ page: "HomePage", prop: onNavigate, hook: hook() });
      return <div>home-stub</div>;
    },
  };
});

const VIEWS: View[] = [
  { name: "overview" }, { name: "collections" }, { name: "new-collection" }, { name: "import-collection" },
  { name: "collection", collectionId: "c" }, { name: "collection-documents", collectionId: "c" },
  { name: "collection-search", collectionId: "c" }, { name: "collection-pipelines", collectionId: "c" },
  { name: "collection-schema", collectionId: "c" }, { name: "collection-activity", collectionId: "c" },
  { name: "collection-settings", collectionId: "c" }, { name: "document", collectionId: "c", documentId: "d" },
  { name: "job", collectionId: "c", jobId: "j" }, { name: "activity" }, { name: "fleet" }, { name: "settings" },
  { name: "api-key", keyId: "k" },
];

describe("route table", () => {
  it("declares exactly one renderer per View variant", () => {
    expect(Object.keys(ROUTES).sort()).toEqual(VIEWS.map((v) => v.name).sort());
    for (const renderer of Object.values(ROUTES)) expect(typeof renderer).toBe("function");
  });

  it("hands the routed entry page the same function useNavigate() returns", () => {
    const navigate: Navigate = vi.fn();
    render(<NavigateProvider navigate={navigate}>{renderRoute({ name: "overview" }, navigate)}</NavigateProvider>);
    expect(screen.getByText("home-stub")).toBeInTheDocument();
    expect(probe.seen).toEqual([{ page: "HomePage", prop: navigate, hook: navigate }]);
  });
});
