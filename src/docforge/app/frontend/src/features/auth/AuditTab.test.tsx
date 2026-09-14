// ====== Code Summary ======
// Render smoke-test for AuditTab: loading -> loaded with rows, and the empty-trail state.

import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AuditPage } from "../../api/audit";
import { AuditTab } from "./AuditTab";

vi.mock("../../api/audit", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/audit")>()),
  listAudit: vi.fn(),
}));

const { listAudit } = await import("../../api/audit");

describe("AuditTab", () => {
  it("shows a loading state, then the audit rows once fetched", async () => {
    const page: AuditPage = {
      entries: [
        {
          id: 1, created_at: "2026-01-01T00:00:00Z", method: "POST", path: "/api/v1/collections/{id}",
          status_code: 201, actor_user_id: null, actor_key_id: "key-1", actor_label: "root",
          target_type: "collection", target_id: "col-123", correlation_id: "corr-abcdef123", client_ip: "10.0.0.1",
        },
      ],
      limit: 50, next_cursor: null,
    };
    vi.mocked(listAudit).mockResolvedValue(page);

    render(<AuditTab />);

    expect(screen.getByText(/loading audit trail/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("root")).toBeInTheDocument());
    expect(screen.getByText("201")).toBeInTheDocument();
    expect(screen.getByText("POST")).toBeInTheDocument();
    expect(screen.queryByText("Load more")).not.toBeInTheDocument();
  });

  it("shows an empty state when the trail has no entries", async () => {
    vi.mocked(listAudit).mockResolvedValue({ entries: [], limit: 50, next_cursor: null });

    render(<AuditTab />);

    await waitFor(() => expect(screen.getByText("No audit activity recorded yet.")).toBeInTheDocument());
  });
});
