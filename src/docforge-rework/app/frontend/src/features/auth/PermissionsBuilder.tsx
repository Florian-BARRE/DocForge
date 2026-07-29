// ====== Code Summary ======
// The permissions half of the create-key form — "full access" vs a scoped grant (capabilities +
// collection scope). Renders nothing scope-related while full access is on, mirroring how
// SearchTargetPicker only shows what the current selection can act on.

import { API_CAPABILITIES, type ApiCapability } from "../../api/auth";
import type { Collection } from "../../api/collections";
import { theme } from "../../theme";

/** `"all"` maps to the backend's `["*"]` sentinel; otherwise an explicit list of collection ids. */
export type CollectionsScope = "all" | string[];

interface PermissionsBuilderProps {
  fullAccess: boolean;
  onFullAccessChange: (fullAccess: boolean) => void;
  capabilities: ApiCapability[];
  onCapabilitiesChange: (capabilities: ApiCapability[]) => void;
  collectionsScope: CollectionsScope;
  onCollectionsScopeChange: (scope: CollectionsScope) => void;
  collections: Collection[] | null;
  /** Set when the collections fetch failed — shown instead of the (misleading) "No collections yet." */
  collectionsError?: string | null;
}

export function PermissionsBuilder({
  fullAccess, onFullAccessChange,
  capabilities, onCapabilitiesChange,
  collectionsScope, onCollectionsScopeChange,
  collections,
  collectionsError,
}: PermissionsBuilderProps) {
  const toggleCapability = (capability: ApiCapability, checked: boolean) => {
    onCapabilitiesChange(
      checked ? [...capabilities, capability] : capabilities.filter((c) => c !== capability),
    );
  };

  const specificIds = collectionsScope === "all" ? [] : collectionsScope;
  const toggleCollection = (id: string, checked: boolean) => {
    const next = checked ? [...specificIds, id] : specificIds.filter((c) => c !== id);
    onCollectionsScopeChange(next);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.s }}>
      <label style={{ display: "flex", alignItems: "center", gap: theme.space.xs, fontSize: theme.font.size.s, color: theme.color.text }}>
        <input type="checkbox" checked={fullAccess} onChange={(e) => onFullAccessChange(e.target.checked)} />
        Full access (every capability, every collection)
      </label>

      {!fullAccess && (
        <div
          style={{
            display: "flex", flexDirection: "column", gap: theme.space.m,
            padding: theme.space.m, border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.m,
          }}
        >
          <div>
            <div style={{ fontSize: theme.font.size.s, color: theme.color.dim, marginBottom: theme.space.xs }}>Capabilities</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.m }}>
              {API_CAPABILITIES.map((capability) => (
                <label
                  key={capability}
                  style={{ display: "flex", alignItems: "center", gap: 4, fontSize: theme.font.size.s, color: theme.color.text }}
                >
                  <input
                    type="checkbox"
                    checked={capabilities.includes(capability)}
                    onChange={(e) => toggleCapability(capability, e.target.checked)}
                  />
                  {capability}
                </label>
              ))}
            </div>
          </div>

          <div>
            <div style={{ fontSize: theme.font.size.s, color: theme.color.dim, marginBottom: theme.space.xs }}>Collections</div>
            <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: theme.font.size.s, color: theme.color.text, marginBottom: theme.space.xs }}>
              <input
                type="checkbox"
                checked={collectionsScope === "all"}
                onChange={(e) => onCollectionsScopeChange(e.target.checked ? "all" : [])}
              />
              All collections (*)
            </label>
            {collectionsScope !== "all" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                {collectionsError && (
                  <span style={{ color: theme.color.error, fontSize: theme.font.size.xs }}>
                    Failed to load collections: {collectionsError}
                  </span>
                )}
                {!collectionsError && collections === null && (
                  <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>loading collections…</span>
                )}
                {!collectionsError && collections?.length === 0 && (
                  <span style={{ color: theme.color.dim, fontSize: theme.font.size.xs }}>No collections yet.</span>
                )}
                {collections?.map((collection) => (
                  <label
                    key={collection.id}
                    style={{ display: "flex", alignItems: "center", gap: 4, fontSize: theme.font.size.s, color: theme.color.text }}
                  >
                    <input
                      type="checkbox"
                      checked={specificIds.includes(collection.id)}
                      onChange={(e) => toggleCollection(collection.id, e.target.checked)}
                    />
                    {collection.name}
                  </label>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
