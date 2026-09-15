// ====== Code Summary ======
// Render smoke-test for DeploymentTab: loading -> loaded (version/services/matrix), and the
// no-services empty state.

import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { CapabilitiesResponse } from "../../api/capabilities";
import { DeploymentTab } from "./DeploymentTab";

vi.mock("../../api/capabilities", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/capabilities")>()),
  getCapabilities: vi.fn(),
}));

const { getCapabilities } = await import("../../api/capabilities");

function fixture(overrides: Partial<CapabilitiesResponse> = {}): CapabilitiesResponse {
  return {
    version: "1.2.3", auth_enabled: true, gpu_present: true,
    services: [{ name: "bge_server", role: "embed", reachable: true, device: "cuda", provides: ["embed"], detail: null }],
    capabilities: { parsers: ["docling"], ocr: [], embed: ["bge_m3"], chunkers: [], vlm: [], llm: [], rerank: [], contextualize: [], metagen: [] },
    ...overrides,
  };
}

describe("DeploymentTab", () => {
  it("shows a loading state, then the deployment summary once fetched", async () => {
    vi.mocked(getCapabilities).mockResolvedValue(fixture());

    render(<DeploymentTab />);

    expect(screen.getByText(/loading deployment info/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("v1.2.3")).toBeInTheDocument());
    expect(screen.getByText("bge_server")).toBeInTheDocument();
    expect(screen.getByText("reachable")).toBeInTheDocument();
    expect(screen.getByText("docling")).toBeInTheDocument();
    expect(screen.getByText(/\/metrics/)).toBeInTheDocument();
  });

  it("shows an empty state when no services are reported", async () => {
    vi.mocked(getCapabilities).mockResolvedValue(fixture({ services: [] }));

    render(<DeploymentTab />);

    await waitFor(() => expect(screen.getByText("No infra services reported.")).toBeInTheDocument());
  });
});
