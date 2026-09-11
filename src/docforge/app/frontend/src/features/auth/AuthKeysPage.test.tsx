// ====== Code Summary ======
// Render smoke-test for the auth-off write-lockdown (round-4 P4 security fix): with
// `capabilities.auth_enabled === false`, the keys list must render read-only — no "+ New key",
// no Rotate/Revoke per row — and the danger-toned AuthOffBanner must be visible. With auth on, the
// write controls are back.

import { render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";
import type { ApiKeyInfo } from "../../api/auth";
import type { CapabilitiesResponse } from "../../api/capabilities";
import { ToastProvider } from "../../shell/toast";
import { AuthKeysPage } from "./AuthKeysPage";

function renderWithProviders(ui: ReactElement) {
  return render(<ToastProvider>{ui}</ToastProvider>);
}

vi.mock("../../api/auth", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/auth")>()),
  listKeys: vi.fn(),
}));
vi.mock("../../api/collections", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/collections")>()),
  listCollections: vi.fn(),
}));
vi.mock("../../api/capabilities", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/capabilities")>()),
  getCapabilities: vi.fn(),
}));

const { listKeys } = await import("../../api/auth");
const { listCollections } = await import("../../api/collections");
const { getCapabilities } = await import("../../api/capabilities");

function keyFixture(overrides: Partial<ApiKeyInfo> = {}): ApiKeyInfo {
  return {
    id: "key-1", name: "root", prefix: "df_abc123", permissions: null,
    created_at: "2026-01-01T00:00:00Z", revoked_at: null, expires_at: null, last_used_at: null,
    ...overrides,
  };
}

function capabilitiesFixture(authEnabled: boolean): CapabilitiesResponse {
  return {
    version: "1.0.0", auth_enabled: authEnabled, gpu_present: null,
    services: [], capabilities: { parsers: [], ocr: [], embed: [], chunkers: [], vlm: [], llm: [], rerank: [], contextualize: [], metagen: [] },
  };
}

describe("AuthKeysPage — auth-off write lockdown", () => {
  it("hides New key / Rotate / Revoke and shows the danger banner when auth is off", async () => {
    vi.mocked(getCapabilities).mockResolvedValue(capabilitiesFixture(false));
    vi.mocked(listKeys).mockResolvedValue([keyFixture()]);
    vi.mocked(listCollections).mockResolvedValue([]);

    renderWithProviders(<AuthKeysPage onNavigate={vi.fn()} />);

    await waitFor(() => expect(screen.getByText("Authentication is disabled")).toBeInTheDocument());
    expect(screen.queryByText("+ New key")).not.toBeInTheDocument();
    expect(screen.queryByText("Rotate")).not.toBeInTheDocument();
    expect(screen.queryByText("Revoke")).not.toBeInTheDocument();
  });

  it("keeps New key / Rotate / Revoke reachable when auth is on", async () => {
    vi.mocked(getCapabilities).mockResolvedValue(capabilitiesFixture(true));
    vi.mocked(listKeys).mockResolvedValue([keyFixture({ name: "ingestion-worker" })]);
    vi.mocked(listCollections).mockResolvedValue([]);

    renderWithProviders(<AuthKeysPage onNavigate={vi.fn()} />);

    await waitFor(() => expect(screen.getByText("+ New key")).toBeInTheDocument());
    expect(screen.getByText("Rotate")).toBeInTheDocument();
    expect(screen.getByText("Revoke")).toBeInTheDocument();
    expect(screen.queryByText("Authentication is disabled")).not.toBeInTheDocument();
  });
});
