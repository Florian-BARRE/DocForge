// ====== Code Summary ======
// The Overview's document-health synthesis — total/enabled/disabled counts, per-status counts,
// and the aggregate page/size footprint — so document-level problems (disabled or failed docs)
// are visible without opening the document explorer.

import type { DocumentListItem } from "../../api/explorer";
import { Chip } from "../../components/Chip";
import { theme as t } from "../../theme";
import type { Navigate } from "../../shell/view";
import { Row, SummaryCard } from "./OverviewCardPrimitives";

interface DocumentHealthCardProps {
  docs: DocumentListItem[] | null;
  collectionId: string;
  onNavigate: Navigate;
}

/** Format a byte count as MB below 1GB, GB above — matches the rest of the app's file-size labels. */
function formatBytes(bytes: number): string {
  const megabytes = bytes / (1024 * 1024);
  return megabytes >= 1024 ? `${(megabytes / 1024).toFixed(2)} GB` : `${megabytes.toFixed(1)} MB`;
}

export function DocumentHealthCard({ docs, collectionId, onNavigate }: DocumentHealthCardProps) {
  const open = () => onNavigate({ name: "collection-documents", collectionId });

  if (docs === null) {
    return (
      <SummaryCard title="Documents" onOpen={open}>
        <span style={{ color: t.color.dim, fontSize: t.font.size.m }}>loading…</span>
      </SummaryCard>
    );
  }

  const enabled = docs.filter((d) => d.enabled).length;
  const disabled = docs.length - enabled;
  const failed = docs.filter((d) => d.status === "failed").length;
  const processing = docs.filter((d) => d.status === "processing").length;
  const pending = docs.filter((d) => d.status === "pending").length;
  const totalPages = docs.reduce((sum, d) => sum + (d.page_count ?? 0), 0);
  const totalBytes = docs.reduce((sum, d) => sum + d.file_size, 0);

  return (
    <SummaryCard title="Documents" onOpen={open}>
      <Row label="Total" value={`${docs.length} document${docs.length === 1 ? "" : "s"}`} />
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        <Chip tone="ok">{enabled} enabled</Chip>
        {disabled > 0 && <Chip tone="warn">{disabled} disabled</Chip>}
        {processing > 0 && <Chip tone="accent">{processing} processing</Chip>}
        {pending > 0 && <Chip tone="dim">{pending} pending</Chip>}
        {failed > 0 && <Chip tone="error">{failed} failed</Chip>}
      </div>
      <Row label="Pages" value={totalPages.toLocaleString()} />
      <Row label="Storage" value={formatBytes(totalBytes)} />
    </SummaryCard>
  );
}
