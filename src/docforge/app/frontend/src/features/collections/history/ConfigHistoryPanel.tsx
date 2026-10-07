// ====== Code Summary ======
// The Settings ▸ History section — the collection's versioned pipeline/search config history:
// the version list (version, date, author, note, change summary), a two-version compare (tick two
// rows → structured diff), and a per-version restore behind a confirm dialog that shows the diff vs
// the current head. Restoring writes a new version, after which the list reloads.

import { useEffect, useState } from "react";
import {
  diffConfigVersions,
  listConfigVersions,
  restoreConfigVersion,
  type ConfigDiffEntry,
  type ConfigVersionSummary,
} from "../../../api/configVersions";
import { Button } from "../../../components/Button";
import { ErrorState } from "../../../components/ErrorState";
import { LoadingState } from "../../../components/LoadingState";
import { theme } from "../../../theme";
import { humanizeRelativeTime } from "../relativeTime";
import { ConfigDiffView } from "./ConfigDiffView";
import { RestoreVersionDialog } from "./RestoreVersionDialog";

const mono = { fontFamily: theme.font.mono, fontSize: theme.font.size.s } as const;

export function ConfigHistoryPanel({ collectionId }: { collectionId: string }) {
  const [items, setItems] = useState<ConfigVersionSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const [compare, setCompare] = useState<ConfigDiffEntry[] | null>(null);
  const [restoring, setRestoring] = useState<number | null>(null);
  const [restoreDiff, setRestoreDiff] = useState<ConfigDiffEntry[] | null>(null);
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const load = () => {
    setError(null);
    listConfigVersions(collectionId)
      .then((page) => setItems(page.items))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  };
  useEffect(load, [collectionId]);

  // Two ticked rows → diff the older into the newer.
  useEffect(() => {
    setCompare(null);
    if (selected.length !== 2) return;
    const [from, to] = [...selected].sort((a, b) => a - b);
    diffConfigVersions(collectionId, from, to)
      .then((d) => setCompare(d.changes))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [collectionId, selected]);

  const head = items?.[0]?.version ?? 0;

  const toggle = (version: number) =>
    setSelected((prev) => (prev.includes(version) ? prev.filter((v) => v !== version) : [...prev, version].slice(-2)));

  const openRestore = (version: number) => {
    setRestoring(version);
    setRestoreDiff(null);
    setRestoreError(null);
    diffConfigVersions(collectionId, head, version)
      .then((d) => setRestoreDiff(d.changes))
      .catch((e) => setRestoreError(e instanceof Error ? e.message : String(e)));
  };

  const confirmRestore = () => {
    if (restoring === null) return;
    setPending(true);
    restoreConfigVersion(collectionId, restoring)
      .then(() => {
        setRestoring(null);
        setSelected([]);
        load();
      })
      .catch((e) => setRestoreError(e instanceof Error ? e.message : String(e)))
      .finally(() => setPending(false));
  };

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!items) return <LoadingState label="loading history…" />;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: theme.space.m }}>
      <div style={{ border: `1px solid ${theme.color.line}`, borderRadius: theme.radius.m, overflow: "hidden" }}>
        {items.map((item) => (
          <div
            key={item.version}
            style={{
              display: "grid", gridTemplateColumns: "24px 56px 110px 140px 1fr auto", alignItems: "center",
              gap: theme.space.s, padding: `${theme.space.s}px ${theme.space.m}px`, borderBottom: `1px solid ${theme.color.line}`,
              fontSize: theme.font.size.m, color: theme.color.text,
            }}
          >
            <input
              type="checkbox"
              aria-label={`Compare v${item.version}`}
              checked={selected.includes(item.version)}
              onChange={() => toggle(item.version)}
            />
            <span style={mono}>v{item.version}</span>
            <span style={{ color: theme.color.dim }} title={item.created_at}>{humanizeRelativeTime(item.created_at)}</span>
            <span>{item.author_label ?? <span style={{ color: theme.color.mute }}>unknown</span>}</span>
            <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0 }}>
              <span>{item.note ?? "—"}</span>
              {(item.changes?.length ?? 0) > 0 && (
                <span style={{ ...mono, color: theme.color.dim }}>{item.changes?.join(" · ")}</span>
              )}
            </div>
            {item.version === head ? (
              <span style={{ color: theme.color.mute, fontSize: theme.font.size.s }}>current</span>
            ) : (
              <Button size="sm" variant="secondary" onClick={() => openRestore(item.version)}>Restore</Button>
            )}
          </div>
        ))}
      </div>

      {selected.length === 2 && (
        <div style={{ display: "flex", flexDirection: "column", gap: theme.space.s }}>
          <div style={{ fontSize: theme.font.size.m, color: theme.color.dim }}>
            Comparing <span style={mono}>v{Math.min(...selected)}</span> → <span style={mono}>v{Math.max(...selected)}</span>
          </div>
          {compare === null ? <LoadingState label="diffing…" /> : <ConfigDiffView changes={compare} />}
        </div>
      )}
      {selected.length < 2 && (
        <div style={{ color: theme.color.mute, fontSize: theme.font.size.s }}>Tick two versions to compare them.</div>
      )}

      {restoring !== null && (
        <RestoreVersionDialog
          version={restoring}
          head={head}
          changes={restoreDiff}
          pending={pending}
          error={restoreError}
          onConfirm={confirmRestore}
          onCancel={() => setRestoring(null)}
        />
      )}
    </div>
  );
}
