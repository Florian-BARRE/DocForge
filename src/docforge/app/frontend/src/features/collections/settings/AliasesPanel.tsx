// ====== Code Summary ======
// The collection Settings "Aliases" section: the aliases pointing at this collection, every other
// alias with its current target and a "Switch alias here" action, and a name input to point a NEW
// alias here. Every switch goes through SwitchAliasDialog (PUT /collection-aliases/{name}) — the
// blue/green cut-over is never a single click. The list is refetched after a switch.

import { useEffect, useState } from "react";
import { listCollectionAliases, setCollectionAlias, type CollectionAlias } from "../../../api/collectionAliases";
import { Button } from "../../../components/Button";
import { inputStyle } from "../../../components/inputStyle";
import { useToast } from "../../../shell/toast";
import { theme } from "../../../theme";
import { SwitchAliasDialog } from "./SwitchAliasDialog";

interface AliasesPanelProps {
  collectionId: string;
  collectionName: string;
}

// Mirror of COLLECTION_ALIAS_PATTERN (shared/…/collection_alias.py) — a client-side hint only;
// the PUT stays the authority (422 on a bad name).
const ALIAS_NAME_PATTERN = /^[a-z0-9][a-z0-9_-]{0,62}$/;

interface PendingSwitch {
  alias: string;
  currentTargetName: string | null;
}

const rowStyle: React.CSSProperties = {
  display: "flex", alignItems: "center", justifyContent: "space-between", gap: theme.space.m,
  padding: `${theme.space.s}px ${theme.space.m}px`, background: theme.color.surface2,
  border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.m, fontSize: theme.font.size.s,
};

export function AliasesPanel({ collectionId, collectionName }: AliasesPanelProps) {
  const toast = useToast();
  const [aliases, setAliases] = useState<CollectionAlias[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [pending, setPending] = useState<PendingSwitch | null>(null);
  const [switching, setSwitching] = useState(false);
  const [switchError, setSwitchError] = useState<string | null>(null);

  const load = () => {
    setLoadError(null);
    listCollectionAliases()
      .then(setAliases)
      .catch((e) => setLoadError(e instanceof Error ? e.message : String(e)));
  };

  useEffect(load, []);

  const openSwitch = (alias: string, currentTargetName: string | null) => {
    setSwitchError(null);
    setPending({ alias, currentTargetName });
  };

  const confirmSwitch = async () => {
    if (!pending) return;
    setSwitching(true);
    setSwitchError(null);
    try {
      await setCollectionAlias(pending.alias, collectionId);
      toast.success(`Alias “${pending.alias}” now points at ${collectionName}.`);
      setPending(null);
      setNewName("");
      load();
    } catch (e) {
      setSwitchError(e instanceof Error ? e.message : String(e));
    } finally {
      setSwitching(false);
    }
  };

  const mine = (aliases ?? []).filter((a) => a.collection_id === collectionId);
  const others = (aliases ?? []).filter((a) => a.collection_id !== collectionId);
  const trimmed = newName.trim();
  const existing = (aliases ?? []).find((a) => a.name === trimmed);
  const newNameValid = ALIAS_NAME_PATTERN.test(trimmed) && existing?.collection_id !== collectionId;
  const mono: React.CSSProperties = { fontFamily: theme.font.mono };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.m }}>
      {loadError && <div style={{ color: theme.color.error, fontSize: theme.font.size.s }}>Failed to load aliases: {loadError}</div>}
      {!loadError && aliases === null && <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>loading aliases…</div>}

      {aliases !== null && (
        <>
          <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
            {mine.length === 0 && (
              <div style={{ color: theme.color.dim, fontSize: theme.font.size.s }}>No alias points at this collection.</div>
            )}
            {mine.map((alias) => (
              <div key={alias.name} style={rowStyle} data-testid="alias-here">
                <span style={mono}>{alias.name}</span>
                <span style={{ color: theme.color.dim }}>points here</span>
              </div>
            ))}
          </div>

          {others.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: theme.space.xs }}>
              {others.map((alias) => (
                <div key={alias.name} style={rowStyle}>
                  <span>
                    <span style={mono}>{alias.name}</span>
                    <span style={{ color: theme.color.dim }}> → {alias.collection_name}</span>
                  </span>
                  <Button size="sm" onClick={() => openSwitch(alias.name, alias.collection_name)}>
                    Switch alias here
                  </Button>
                </div>
              ))}
            </div>
          )}

          <div style={{ display: "flex", gap: theme.space.s, alignItems: "center" }}>
            <input
              aria-label="New alias name"
              style={{ ...inputStyle, maxWidth: 320 }}
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="e.g. contracts-live"
            />
            <Button
              size="sm"
              disabled={!newNameValid}
              onClick={() => openSwitch(trimmed, existing ? existing.collection_name : null)}
            >
              Point alias here
            </Button>
          </div>
        </>
      )}

      {pending && (
        <SwitchAliasDialog
          alias={pending.alias}
          currentTargetName={pending.currentTargetName}
          collectionName={collectionName}
          pending={switching}
          error={switchError}
          onConfirm={confirmSwitch}
          onCancel={() => setPending(null)}
        />
      )}
    </div>
  );
}
