// ====== Code Summary ======
// The permissions half of the create-key form — "full access" vs a scoped grant (a named usage
// profile OR a custom capability list, + collection scope: explicit collections and/or `alias:<name>`
// entries). Renders nothing scope-related while full access is on, mirroring how
// SearchTargetPicker only shows what the current selection can act on.

import { API_CAPABILITIES, KEY_PROFILES, type ApiCapability, type KeyProfile } from "../../api/auth";
import { ALIAS_SCOPE_PREFIX, type CollectionAlias } from "../../api/collectionAliases";
import type { Collection } from "../../api/collections";
import { inputStyle } from "../../components/inputStyle";
import { theme } from "../../theme";

/**
 * `"all"` maps to the backend's `["*"]` sentinel; otherwise an explicit list of collection ids and/or
 * `alias:<name>` entries (an alias entry follows the alias's CURRENT target).
 */
export type CollectionsScope = "all" | string[];

interface PermissionsBuilderProps {
  fullAccess: boolean;
  onFullAccessChange: (fullAccess: boolean) => void;
  /** `null` = custom: the capability checkboxes define the grant. */
  profile: KeyProfile | null;
  onProfileChange: (profile: KeyProfile | null) => void;
  capabilities: ApiCapability[];
  onCapabilitiesChange: (capabilities: ApiCapability[]) => void;
  collectionsScope: CollectionsScope;
  onCollectionsScopeChange: (scope: CollectionsScope) => void;
  collections: Collection[] | null;
  /** Set when the collections fetch failed — shown instead of the (misleading) "No collections yet." */
  collectionsError?: string | null;
  /** The aliases a key can be scoped to (`alias:<name>`); null while loading, omitted = none offered. */
  aliases?: CollectionAlias[] | null;
}

// The <select> value standing for "no preset — pick the capabilities by hand".
const CUSTOM_PROFILE = "custom";

const sectionLabelStyle: React.CSSProperties = {
  fontSize: theme.font.size.xs, color: theme.color.dim, marginBottom: theme.space.xs,
  textTransform: "uppercase", letterSpacing: "0.04em", fontWeight: 600,
};

const checkboxLabelStyle: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 6, fontSize: theme.font.size.s, color: theme.color.text,
};

export function PermissionsBuilder({
  fullAccess, onFullAccessChange,
  profile, onProfileChange,
  capabilities, onCapabilitiesChange,
  collectionsScope, onCollectionsScopeChange,
  collections,
  collectionsError,
  aliases = [],
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
      <label
        style={{
          display: "flex", alignItems: "center", gap: theme.space.s, fontSize: theme.font.size.s, color: theme.color.text,
          fontWeight: fullAccess ? theme.font.weight.semibold : theme.font.weight.normal,
          background: fullAccess ? theme.color.surface3 : theme.color.surface2,
          border: `1px solid ${fullAccess ? theme.color.lineStrong : theme.color.line}`,
          borderRadius: theme.radius.m, padding: `${theme.space.s}px ${theme.space.m}px`,
        }}
      >
        <input type="checkbox" checked={fullAccess} onChange={(e) => onFullAccessChange(e.target.checked)} />
        <span>Full access <span style={{ color: theme.color.dim, fontWeight: theme.font.weight.normal }}>— every capability, every collection</span></span>
      </label>

      {!fullAccess && (
        <div
          style={{
            display: "flex", flexDirection: "column", gap: theme.space.m,
            padding: theme.space.m, background: theme.color.surface2,
            border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.m,
          }}
        >
          <div>
            <div style={sectionLabelStyle}>Profile</div>
            <select
              aria-label="Profile"
              style={inputStyle}
              value={profile ?? CUSTOM_PROFILE}
              onChange={(e) => onProfileChange(e.target.value === CUSTOM_PROFILE ? null : (e.target.value as KeyProfile))}
            >
              {KEY_PROFILES.map(({ value }) => <option key={value} value={value}>{value}</option>)}
              <option value={CUSTOM_PROFILE}>custom — pick capabilities</option>
            </select>
            {profile && (
              <div style={{ color: theme.color.dim, fontSize: theme.font.size.xs, marginTop: theme.space.xs }}>
                {KEY_PROFILES.find((p) => p.value === profile)?.hint}
              </div>
            )}
          </div>

          {profile === null && <div>
            <div style={sectionLabelStyle}>Capabilities</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: theme.space.m }}>
              {API_CAPABILITIES.map((capability) => (
                <label key={capability} style={checkboxLabelStyle}>
                  <input
                    type="checkbox"
                    checked={capabilities.includes(capability)}
                    onChange={(e) => toggleCapability(capability, e.target.checked)}
                  />
                  {capability}
                </label>
              ))}
            </div>
          </div>}

          <div>
            <div style={sectionLabelStyle}>Collections</div>
            <label style={{ ...checkboxLabelStyle, marginBottom: theme.space.xs }}>
              <input
                type="checkbox"
                checked={collectionsScope === "all"}
                onChange={(e) => onCollectionsScopeChange(e.target.checked ? "all" : [])}
              />
              All collections (*)
            </label>
            {collectionsScope !== "all" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
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
                  <label key={collection.id} style={checkboxLabelStyle}>
                    <input
                      type="checkbox"
                      checked={specificIds.includes(collection.id)}
                      onChange={(e) => toggleCollection(collection.id, e.target.checked)}
                    />
                    {collection.name}
                  </label>
                ))}
                {aliases && aliases.length > 0 && (
                  <div style={{ ...sectionLabelStyle, marginTop: theme.space.s }}>Aliases — follow the current target</div>
                )}
                {aliases?.map((alias) => {
                  const entry = `${ALIAS_SCOPE_PREFIX}${alias.name}`;
                  return (
                    <label key={entry} style={checkboxLabelStyle}>
                      <input
                        type="checkbox"
                        checked={specificIds.includes(entry)}
                        onChange={(e) => toggleCollection(entry, e.target.checked)}
                      />
                      <span style={{ fontFamily: theme.font.mono }}>{entry}</span>
                      <span style={{ color: theme.color.dim }}>→ {alias.collection_name}</span>
                    </label>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
