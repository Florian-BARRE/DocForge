// ====== Code Summary ======
// Render test for PermissionsBuilder's usage-profile picker — a named profile hides the capability
// checkboxes (the server expands the preset), "custom" reveals them, and picking emits the change.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PermissionsBuilder } from "./PermissionsBuilder";

function renderBuilder(profile: "agent_reader" | null, onProfileChange = vi.fn()) {
  render(
    <PermissionsBuilder
      fullAccess={false}
      onFullAccessChange={vi.fn()}
      profile={profile}
      onProfileChange={onProfileChange}
      capabilities={["read_text"]}
      onCapabilitiesChange={vi.fn()}
      collectionsScope="all"
      onCollectionsScopeChange={vi.fn()}
      collections={[]}
    />,
  );
  return onProfileChange;
}

describe("PermissionsBuilder profiles", () => {
  it("hides the capability checkboxes while a profile is selected", () => {
    renderBuilder("agent_reader");
    expect(screen.getByLabelText("Profile")).toHaveValue("agent_reader");
    expect(screen.queryByText("read_technical")).toBeNull();
  });

  it("shows the canonical capabilities (never the legacy read) for a custom grant", () => {
    renderBuilder(null);
    expect(screen.getByText("read_technical")).toBeInTheDocument();
    expect(screen.queryByText(/^read$/)).toBeNull();
  });

  it("emits null when switching to custom", () => {
    const onProfileChange = renderBuilder("agent_reader");
    fireEvent.change(screen.getByLabelText("Profile"), { target: { value: "custom" } });
    expect(onProfileChange).toHaveBeenCalledWith(null);
  });
});

describe("PermissionsBuilder alias scope", () => {
  it("offers alias:<name> entries and emits them into the explicit scope", () => {
    const onScope = vi.fn();
    render(
      <PermissionsBuilder
        fullAccess={false}
        onFullAccessChange={vi.fn()}
        profile="agent_reader"
        onProfileChange={vi.fn()}
        capabilities={["read_text"]}
        onCapabilitiesChange={vi.fn()}
        collectionsScope={["c9"]}
        onCollectionsScopeChange={onScope}
        collections={[]}
        aliases={[{ name: "docs-live", collection_id: "c1", collection_name: "docs-blue", created_at: "x", updated_at: "x" }]}
      />,
    );
    expect(screen.getByText("→ docs-blue")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText(/alias:docs-live/));
    expect(onScope).toHaveBeenCalledWith(["c9", "alias:docs-live"]);
  });
});
