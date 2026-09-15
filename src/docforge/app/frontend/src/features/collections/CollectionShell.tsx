// ====== Code Summary ======
// The collection workspace chrome — now a CONTENT FRAME, not a nav owner. Since the IA redesign the
// persistent left rail SWAPS to the collection's nav while you're inside one (see
// shell/sidebar/collectionSidebarConfig.tsx), so this shell no longer renders a horizontal section/
// sub-tab strip. It keeps only: the header (breadcrumb + name + needs-reindex chip + contract
// subtitle + Settings/Upload actions), the upload panel, and — the sole remaining in-content
// sub-nav — the Ingestion | Search toggle shown while on the Pipelines page (the two editors live
// at equal depth under one rail item). Export and Delete moved to Settings ▸ Transfer / ▸ Danger
// zone (settings/CollectionSettingsPage) — no longer duplicated here. Fetches the collection only
// to render this chrome; each nested page still owns its own data fetch.

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { getCollection, type Collection } from "../../api/collections";
import { Breadcrumb, type BreadcrumbItem } from "../../components/Breadcrumb";
import { Button } from "../../components/Button";
import { Chip } from "../../components/Chip";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { PageHeader } from "../../components/PageHeader";
import { TabNav, type TabItem } from "../../components/TabNav";
import type { Navigate } from "../../shell/view";
import { theme as t } from "../../theme";
import { BreadcrumbExtraContext } from "../../shell/collectionBreadcrumbExtra";
import { UploadPanel } from "./UploadPanel";
import { bytesToMb } from "./wizard/wizardTypes";

// Lets a nested page (namely the empty-collection Overview hero) hide the shell header's "Upload"
// toggle so it never opens a second upload panel alongside a page's own inline one — see
// `useHideHeaderUpload`. Context, not a prop, because the nested page is passed in as `children`
// from `App.tsx` (a sibling of this component's own state) yet renders inside this tree.
const HideHeaderUploadContext = createContext<((hide: boolean) => void) | null>(null);

/**
 * Hide (or restore) the collection shell's header "Upload" toggle from a nested page.
 *
 * A no-op outside a `CollectionShell` (context absent) so a page using this hook never crashes if
 * rendered standalone.
 *
 * @param hide - Whether the header's Upload action should be hidden right now.
 */
export function useHideHeaderUpload(hide: boolean): void {
  const setHidden = useContext(HideHeaderUploadContext);
  useEffect(() => {
    setHidden?.(hide);
    return () => setHidden?.(false);
  }, [hide, setHidden]);
}

/** Which pipeline editor is showing — the only in-content sub-nav left in the shell. */
export type PipelineStage = "ingestion" | "search";

const PIPELINE_STAGES: TabItem<PipelineStage>[] = [
  { key: "ingestion", label: "Ingestion" },
  { key: "search", label: "Search" },
];

interface CollectionShellProps {
  collectionId: string;
  onNavigate: Navigate;
  children: ReactNode;
  /** Set only on the Pipelines page — renders the Ingestion | Search sub-tab bar and marks the active
   *  editor. Absent on every other tab (no in-content sub-nav there). */
  pipelineStage?: PipelineStage;
}

export function CollectionShell({ collectionId, onNavigate, children, pipelineStage }: CollectionShellProps) {
  const [collection, setCollection] = useState<Collection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  // Set by a nested page via `useHideHeaderUpload` (namely the empty-collection Overview hero) so
  // the header action never opens a second upload panel next to that page's own inline one.
  const [uploadActionHidden, setUploadActionHidden] = useState(false);
  // Set by a nested page via `useCollectionBreadcrumbExtra` (namely DocumentPage) so this shell's
  // own breadcrumb can grow into the page's full trail instead of that page stacking a second one.
  const [breadcrumbExtra, setBreadcrumbExtra] = useState<BreadcrumbItem[] | null>(null);

  const hideUploadAction = useCallback((hide: boolean) => {
    setUploadActionHidden(hide);
    if (hide) setShowUpload(false);
  }, []);

  const load = () => {
    setError(null);
    getCollection(collectionId)
      .then(setCollection)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  };

  useEffect(load, [collectionId]);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!collection) return <LoadingState label="loading collection…" />;

  // "Collections / {collection}" alone, or — when a nested page (e.g. DocumentPage) contributed
  // trailing segments via `useCollectionBreadcrumbExtra` — "Collections / {collection} / …extra".
  const breadcrumbItems: BreadcrumbItem[] = breadcrumbExtra
    ? [
        { label: "Collections", view: { name: "collections" } },
        { label: collection.name, view: { name: "collection", collectionId } },
        ...breadcrumbExtra,
      ]
    : [
        { label: "Collections", view: { name: "collections" } },
        { label: collection.name },
      ];

  const maxSizeMb = bytesToMb(collection.max_file_size_bytes);
  const subtitle = `${collection.supported_formats.join(", ")} · ${maxSizeMb} MiB max · `
    + `${collection.fields.length} field${collection.fields.length === 1 ? "" : "s"}`;

  return (
    <div className="df-rise" style={{ height: "100%", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div style={{ padding: `${t.space.m}px ${t.space.xl}px 0`, maxWidth: 1200, margin: "0 auto", width: "100%" }}>
        <PageHeader
          compact
          eyebrow={<Breadcrumb items={breadcrumbItems} onNavigate={onNavigate} />}
          title={
            <span style={{ display: "inline-flex", alignItems: "center", gap: t.space.s }}>
              {collection.name}
              {collection.needs_reindex && <Chip tone="warn">needs reindex</Chip>}
            </span>
          }
          subtitle={subtitle}
          actions={
            <>
              <Button variant="secondary" onClick={() => onNavigate({ name: "collection-settings", collectionId })}>Settings</Button>
              {!uploadActionHidden && (
                <Button
                  variant="primary"
                  onClick={() => setShowUpload((v) => !v)}
                >
                  {showUpload ? "Cancel upload" : "Upload"}
                </Button>
              )}
            </>
          }
        />
        {showUpload && !uploadActionHidden && (
          <div className="df-rise" style={{ marginBottom: t.space.l, maxWidth: 480 }}>
            <UploadPanel
              collectionId={collectionId}
              fields={collection.fields}
              onUploaded={(jobId, count) => {
                setShowUpload(false);
                onNavigate(count > 1 ? { name: "collection-activity", collectionId } : { name: "job", collectionId, jobId });
              }}
            />
          </div>
        )}

        {/* The only in-content sub-nav left: the two pipeline editors at equal depth. */}
        {pipelineStage && (
          <TabNav
            tabs={PIPELINE_STAGES}
            active={pipelineStage}
            onSelect={(stage) => onNavigate({ name: "collection-pipelines", collectionId, stage })}
            navId="collection-pipeline-stage"
            ariaLabel="Pipeline editors"
            panelId="collection-panel"
          />
        )}
      </div>
      <div id="collection-panel" style={{ flex: 1, minHeight: 0 }}>
        <HideHeaderUploadContext.Provider value={hideUploadAction}>
          <BreadcrumbExtraContext.Provider value={setBreadcrumbExtra}>
            {children}
          </BreadcrumbExtraContext.Provider>
        </HideHeaderUploadContext.Provider>
      </div>
    </div>
  );
}
