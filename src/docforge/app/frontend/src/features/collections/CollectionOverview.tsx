// ====== Code Summary ======
// The collection's Overview tab — a health & activity console: a headline verdict banner, headline
// stat tiles, the ingestion-jobs and document-health synthesis cards, then the Metadata / Ingestion
// pipeline / Search summary cards. Read-only; the real editing lives in Metadata / the pipeline
// studios. Fetches the collection, its documents and its ingestion jobs.

import { useEffect, useState } from "react";
import { getCollection, type Collection, type FieldSpec } from "../../api/collections";
import { listDocuments, type DocumentListItem } from "../../api/explorer";
import { listJobs, type JobStatus } from "../../api/jobs";
import { Button } from "../../components/Button";
import { Chip } from "../../components/Chip";
import { ErrorState } from "../../components/ErrorState";
import { LoadingState } from "../../components/LoadingState";
import type { Navigate, View } from "../../shell/view";
import { theme as t } from "../../theme";
import { DocumentHealthCard } from "./DocumentHealthCard";
import { HealthBanner } from "./HealthBanner";
import { JobsSummaryCard } from "./JobsSummaryCard";
import { Row, StatTile, SummaryCard } from "./OverviewCardPrimitives";
import { ReindexBanner } from "./ReindexBanner";

interface Props {
  collectionId: string;
  onNavigate: Navigate;
}

/** Recursively collect the kinds present per family in a stored pipeline blob (groups + foreach). */
function kindsByFamily(node: unknown, acc: Record<string, Set<string>>): Record<string, Set<string>> {
  if (!node || typeof node !== "object") return acc;
  const n = node as Record<string, unknown>;
  if (typeof n.family === "string" && typeof n.kind === "string") {
    (acc[n.family] ??= new Set()).add(n.kind);
  }
  for (const child of (n.nodes as unknown[]) ?? []) kindsByFamily(child, acc);
  if (n.body) kindsByFamily(n.body, acc);
  return acc;
}

export function CollectionOverview({ collectionId, onNavigate }: Props) {
  const [collection, setCollection] = useState<Collection | null>(null);
  const [docs, setDocs] = useState<DocumentListItem[] | null>(null);
  const [jobs, setJobs] = useState<JobStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setError(null);
    getCollection(collectionId).then(setCollection).catch((e) => setError(e instanceof Error ? e.message : String(e)));
    listDocuments(collectionId).then(setDocs).catch(() => setDocs([]));
    listJobs(collectionId).then(setJobs).catch(() => setJobs([]));
  };
  useEffect(load, [collectionId]);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!collection) return <LoadingState label="loading overview…" />;

  const go = (v: View) => onNavigate(v);
  const fields: FieldSpec[] = collection.fields;
  const filterable = fields.filter((f) => f.filterable).length;
  const semantic = fields.filter((f) => f.semantic).length;
  const lexical = fields.filter((f) => f.lexical).length;
  const required = fields.filter((f) => f.required).length;
  const generated = fields.filter((f) => f.origin === "generated").length;
  const enabledDocs = docs?.filter((d) => d.enabled).length ?? 0;
  const maxSizeMb = (collection.max_file_size_bytes / (1024 * 1024)).toFixed(1);
  const kinds = kindsByFamily(collection.pipeline, {});
  const one = (fam: string) => [...(kinds[fam] ?? [])].join(", ") || "—";
  const stageCount = Object.values(kinds).reduce((s, set) => s + set.size, 0);
  const searchCustom = collection.search && Object.keys(collection.search).length > 0;

  return (
    <div className="df-rise" style={{ padding: t.space.xl, overflowY: "auto", height: "100%", maxWidth: 1100, margin: "0 auto", width: "100%" }}>
      {collection.needs_reindex && <div style={{ marginBottom: t.space.l }}><ReindexBanner /></div>}

      <HealthBanner collection={collection} jobs={jobs} docs={docs} />

      {/* Headline stats. */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: t.space.m, marginBottom: t.space.xl }}>
        <StatTile label="Documents" value={docs ? docs.length : "…"} sub={docs ? `${enabledDocs} enabled` : undefined} />
        <StatTile label="Metadata fields" value={fields.length} sub={`${required} required · ${generated} generated`} />
        <StatTile label="Searchable" value={`${filterable + semantic + lexical}`} sub={`${filterable} filter · ${semantic} semantic · ${lexical} lexical`} />
        <StatTile label="Formats" value={collection.supported_formats.length} sub={collection.supported_formats.join(", ")} />
        <StatTile label="Max file" value={`${maxSizeMb} MB`} sub={collection.created_at ? `created ${new Date(collection.created_at).toLocaleDateString()}` : undefined} />
      </div>

      {/* Activity + document health. */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: t.space.l, marginBottom: t.space.l }}>
        <JobsSummaryCard jobs={jobs} docs={docs} collectionId={collectionId} onNavigate={onNavigate} />
        <DocumentHealthCard docs={docs} collectionId={collectionId} onNavigate={onNavigate} />
      </div>

      {/* Config summary cards. */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: t.space.l }}>
        <SummaryCard title="Metadata" onOpen={() => go({ name: "collection-metadata", collectionId })}>
          <Row label="Fields" value={<>{fields.length} <span style={{ color: t.color.dim, fontSize: t.font.size.m }}>({required} required)</span></>} />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            <Chip tone="accent">{filterable} filterable</Chip>
            <Chip tone="ok">{semantic} semantic</Chip>
            <Chip tone="loop">{lexical} lexical</Chip>
            {generated > 0 && <Chip tone="neutral">{generated} generated</Chip>}
          </div>
        </SummaryCard>

        <SummaryCard title="Ingestion pipeline" onOpen={() => go({ name: "collection-pipeline", collectionId })}>
          <Row label="Parser" value={<span className="mono">{one("parser")}</span>} />
          <Row label="Embedder" value={<span className="mono">{one("embed")}</span>} />
          <Row label="Chunker" value={<span className="mono">{one("chunker")}</span>} />
          <Row label="Nodes" value={`${stageCount} across ${Object.keys(kinds).length} families`} />
        </SummaryCard>

        <SummaryCard title="Search" onOpen={() => go({ name: "collection-search", collectionId })}>
          <Row label="Config" value={searchCustom ? <Chip tone="accent">custom graph</Chip> : <Chip tone="neutral">stock default</Chip>} />
          <Row label="Surfaces" value={`${semantic} semantic · ${lexical} lexical meta`} />
          <div><Button size="sm" variant="secondary" onClick={() => go({ name: "collection-search", collectionId })}>Run a search →</Button></div>
        </SummaryCard>
      </div>
    </div>
  );
}
