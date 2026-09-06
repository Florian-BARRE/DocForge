// ====== Code Summary ======
// The collection workspace chrome — a header (name + contract summary + upload/edit actions) and a
// TWO-LEVEL nav shared by every view nested under a collection. Level 1 is Overview | Corpus | Search
// | Jobs; level 2 is the active section's sub-tabs (Corpus → Metadata · Ingestion pipeline · Documents;
// Search → Search · Search pipeline; Overview and Jobs are leaves). A document's detail view is nested
// under Corpus›Documents, so the nav stays visible while inspecting a document. Fetches the collection
// only to render this chrome — each nested page still owns its own data fetch.

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { getCollection, type Collection } from "../../api/collections";
import { Breadcrumb, type BreadcrumbItem } from "../../components/Breadcrumb";
import { Button } from "../../components/Button";
import { Chip } from "../../components/Chip";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import { OverflowMenu } from "../../components/OverflowMenu";
import { OverflowMenuItem } from "../../components/OverflowMenuItem";
import { PageHeader } from "../../components/PageHeader";
import { TabNav, tabButtonId, type TabItem } from "../../components/TabNav";
import { useRovingTabIndex } from "../../components/useRovingTabIndex";
import type { Navigate, View } from "../../shell/view";
import { theme as t } from "../../theme";
import { DeleteCollectionDialog } from "./DeleteCollectionDialog";
import { useDeleteCollection } from "./state/useDeleteCollection";
import { BreadcrumbExtraContext } from "../../shell/collectionBreadcrumbExtra";
import { ExportPanel } from "./transfer/ExportPanel";
import { UploadPanel } from "./UploadPanel";

// Lets a nested page (namely the empty-collection Overview hero) hide the shell header's "Upload"
// toggle so it never opens a second upload panel alongside a page's own inline one — see
// `useHideHeaderUpload`. Context, not a prop, because the nested page is passed in as `children`
// from `App.tsx` (a sibling of this component's own state, not a descendant that could receive props
// directly) yet still renders inside this component's tree, where context does reach it.
const HideHeaderUploadContext = createContext<((hide: boolean) => void) | null>(null);

/**
 * Hide (or restore) the collection shell's header "Upload" toggle from a nested page.
 *
 * A no-op outside a `CollectionShell` (context absent) so a page using this hook never crashes if
 * rendered standalone (e.g. in isolation during a future test).
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

// A tab key — the caller passes the active one; the section (level-1 group) is derived from it.
export type CollectionTabKey =
  | "overview"                                      // Overview (leaf)
  | "metadata" | "pipeline" | "documents"          // Corpus
  | "search" | "search-pipeline"                   // Search
  | "jobs";                                         // Jobs (leaf)

type Section = "overview" | "corpus" | "search" | "jobs";

const SECTION_ORDER: { key: Section; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "corpus", label: "Corpus" },
  { key: "search", label: "Search" },
  { key: "jobs", label: "Jobs" },
];

const SECTION_OF: Record<CollectionTabKey, Section> = {
  overview: "overview",
  metadata: "corpus", pipeline: "corpus", documents: "corpus",
  search: "search", "search-pipeline": "search",
  jobs: "jobs",
};

// Level-2 sub-tabs per section — Overview and Jobs are leaf tabs (no sub-tabs).
const SUBTABS: Record<Section, TabItem<CollectionTabKey>[]> = {
  overview: [],
  corpus: [
    { key: "metadata", label: "Metadata" },
    { key: "pipeline", label: "Ingestion pipeline" },
    { key: "documents", label: "Documents" },
  ],
  search: [
    { key: "search", label: "Search" },
    { key: "search-pipeline", label: "Search pipeline" },
  ],
  jobs: [],
};

// The landing tab when a level-1 section is clicked.
const SECTION_DEFAULT: Record<Section, CollectionTabKey> = {
  overview: "overview", corpus: "documents", search: "search", jobs: "jobs",
};

function viewForTab(tab: CollectionTabKey, collectionId: string): View {
  switch (tab) {
    case "overview": return { name: "collection", collectionId };
    case "metadata": return { name: "collection-metadata", collectionId };
    case "pipeline": return { name: "collection-pipeline", collectionId };
    case "documents": return { name: "collection-documents", collectionId };
    case "search": return { name: "collection-search", collectionId };
    case "search-pipeline": return { name: "collection-search-pipeline", collectionId };
    case "jobs": return { name: "collection-jobs", collectionId };
  }
}

interface CollectionShellProps {
  collectionId: string;
  active: CollectionTabKey;
  onNavigate: Navigate;
  children: ReactNode;
}

/** Deterministic id for a level-1 section tab — used for both roving focus and the panel's `aria-labelledby`. */
function sectionTabId(key: Section): string {
  return `collection-section-tab-${key}`;
}

interface SectionTabProps {
  sectionKey: Section;
  active: boolean;
  label: string;
  onClick: () => void;
  registerRef: (el: HTMLElement | null) => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
}

function SectionTab({ sectionKey, active, label, onClick, registerRef, onKeyDown }: SectionTabProps) {
  return (
    <button
      id={sectionTabId(sectionKey)}
      ref={registerRef}
      role="tab"
      aria-selected={active}
      tabIndex={active ? 0 : -1}
      onClick={onClick}
      onKeyDown={onKeyDown}
      style={{
        background: active ? t.color.accentSoft : "transparent",
        color: active ? t.color.accentSafe : t.color.dim,
        border: `1px solid ${active ? t.color.accentLine : "transparent"}`,
        borderRadius: t.radius.m, padding: "4px 13px",
        fontSize: t.font.size.m, fontWeight: active ? 700 : 600, cursor: "pointer",
        transition: "background .16s ease, color .16s ease, border-color .16s ease",
      }}
    >
      {label}
    </button>
  );
}

export function CollectionShell({ collectionId, active, onNavigate, children }: CollectionShellProps) {
  const [collection, setCollection] = useState<Collection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const [showExport, setShowExport] = useState(false);
  // Set by a nested page via `useHideHeaderUpload` (namely the empty-collection Overview hero) so
  // the header action never opens a second upload panel next to that page's own inline one.
  const [uploadActionHidden, setUploadActionHidden] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  // Set by a nested page via `useCollectionBreadcrumbExtra` (namely DocumentPage) so this shell's
  // own breadcrumb can grow into the page's full trail instead of that page stacking a second one.
  const [breadcrumbExtra, setBreadcrumbExtra] = useState<BreadcrumbItem[] | null>(null);
  const { deleting, error: deleteError, remove } = useDeleteCollection();

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

  // Called unconditionally (before the early returns below) — the Rules of Hooks require the same
  // hooks on every render regardless of the loading/error branches.
  const sectionRoving = useRovingTabIndex(
    SECTION_ORDER.map((s) => s.key),
    (key) => onNavigate(viewForTab(SECTION_DEFAULT[key], collectionId)),
  );

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!collection) return <LoadingState label="loading collection…" />;

  const handleConfirmDelete = async () => {
    const ok = await remove({ id: collectionId, name: collection.name });
    if (ok) {
      setConfirmingDelete(false);
      onNavigate({ name: "collections" });
    }
  };

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

  const section = SECTION_OF[active];
  const maxSizeMb = (collection.max_file_size_bytes / (1024 * 1024)).toFixed(1);
  const subtitle = `${collection.supported_formats.join(", ")} · ${maxSizeMb} MB max · `
    + `${collection.fields.length} field${collection.fields.length === 1 ? "" : "s"}`;

  // The panel below is `aria-labelledby` whichever tab strip is actually "in charge" of it right
  // now — the level-2 sub-tabs when the section has any, otherwise the level-1 section tab itself
  // (Overview/Jobs are leaves with no sub-tabs).
  const activeTabId = SUBTABS[section].length > 1 ? tabButtonId("collection-subtabs", active) : sectionTabId(section);

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
              <Button variant="secondary" onClick={() => onNavigate({ name: "collection-edit", collectionId })}>Edit</Button>
              <Button
                variant="secondary"
                onClick={() => { setShowExport((v) => !v); setShowUpload(false); }}
              >
                {showExport ? "Cancel export" : "Export"}
              </Button>
              {!uploadActionHidden && (
                <Button
                  variant="primary"
                  onClick={() => { setShowUpload((v) => !v); setShowExport(false); }}
                >
                  {showUpload ? "Cancel upload" : "Upload"}
                </Button>
              )}
              <OverflowMenu label={`More actions for ${collection.name}`}>
                <OverflowMenuItem tone="danger" onClick={() => setConfirmingDelete(true)}>Delete collection</OverflowMenuItem>
              </OverflowMenu>
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
                onNavigate(count > 1 ? { name: "collection-jobs", collectionId } : { name: "job", collectionId, jobId });
              }}
            />
          </div>
        )}
        {showExport && (
          <div className="df-rise" style={{ marginBottom: t.space.l, maxWidth: 480 }}>
            <ExportPanel collectionId={collectionId} collectionName={collection.name} />
          </div>
        )}

        {/* Level 1 — Overview | Corpus | Search | Jobs. */}
        <div
          role="tablist"
          aria-label="Collection sections"
          style={{
            display: "flex", gap: t.space.xs,
            marginBottom: SUBTABS[section].length > 1 ? t.space.s : 0,
            borderBottom: SUBTABS[section].length > 1 ? "none" : `1px solid ${t.color.line}`,
            paddingBottom: SUBTABS[section].length > 1 ? 0 : t.space.s,
          }}
        >
          {SECTION_ORDER.map((s) => (
            <SectionTab
              key={s.key}
              sectionKey={s.key}
              active={section === s.key}
              label={s.label}
              onClick={() => onNavigate(viewForTab(SECTION_DEFAULT[s.key], collectionId))}
              registerRef={sectionRoving.register(s.key)}
              onKeyDown={(e) => sectionRoving.onKeyDown(e, s.key)}
            />
          ))}
        </div>
        {/* Level 2 — the active section's sub-tabs (Overview/Jobs have none). */}
        {SUBTABS[section].length > 1 && (
          <TabNav
            tabs={SUBTABS[section]}
            active={active}
            onSelect={(tab) => onNavigate(viewForTab(tab, collectionId))}
            navId="collection-subtabs"
            ariaLabel={`${SECTION_ORDER.find((s) => s.key === section)?.label ?? "Section"} views`}
            panelId="collection-panel"
          />
        )}
      </div>
      <div role="tabpanel" id="collection-panel" aria-labelledby={activeTabId} style={{ flex: 1, minHeight: 0 }}>
        <HideHeaderUploadContext.Provider value={hideUploadAction}>
          <BreadcrumbExtraContext.Provider value={setBreadcrumbExtra}>
            {children}
          </BreadcrumbExtraContext.Provider>
        </HideHeaderUploadContext.Provider>
      </div>
      {confirmingDelete && (
        <DeleteCollectionDialog
          collectionName={collection.name}
          pending={deleting}
          error={deleteError}
          onConfirm={handleConfirmDelete}
          onCancel={() => setConfirmingDelete(false)}
        />
      )}
    </div>
  );
}
