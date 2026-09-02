// ====== Code Summary ======
// A slim strip of quick-glance stat chips below the provider health board — documents, metadata
// fields, indexed vectors, formats, and max file size, each a one-click jump to the tab that owns
// that detail. Deliberately NOT a card grid: the health board is the Overview's hero, this is a
// secondary summary.

import type { Collection, CollectionHealth, FieldSpec } from "../../api/collections";
import type { DocumentListItem } from "../../api/explorer";
import type { Navigate } from "../../shell/view";
import { theme as t } from "../../theme";
import { lastIngestLabel } from "./collectionHealth";
import { MetaLine, StatChip } from "./OverviewCardPrimitives";

interface OverviewStatStripProps {
  collection: Collection;
  docs: DocumentListItem[] | null;
  fields: FieldSpec[];
  health: CollectionHealth | null;
  collectionId: string;
  onNavigate: Navigate;
}

export function OverviewStatStrip({ collection, docs, fields, health, collectionId, onNavigate }: OverviewStatStripProps) {
  const enabledDocs = docs?.filter((d) => d.enabled).length ?? 0;
  const requiredFields = fields.filter((f) => f.required).length;
  const maxSizeMb = (collection.max_file_size_bytes / (1024 * 1024)).toFixed(1);
  const vectorCount = health?.search.index.vector_count;

  return (
    <>
      {/* Facts ABOUT the collection, not about any one tile — kept out of the chips below so each
          chip's sub-label stays scoped to its own metric. */}
      <MetaLine
        items={[
          collection.created_at ? `created ${new Date(collection.created_at).toLocaleDateString()}` : null,
          `last ingest ${lastIngestLabel(health, collection.created_at)}`,
        ]}
      />
      <div style={{ display: "flex", flexWrap: "wrap", gap: t.space.m, marginBottom: t.space.xl }}>
        <StatChip
          label="Documents"
          value={docs ? docs.length : "…"}
          sub={docs ? `${enabledDocs} enabled` : undefined}
          onClick={() => onNavigate({ name: "collection-documents", collectionId })}
        />
        <StatChip
          label="Metadata fields"
          value={fields.length}
          sub={`${requiredFields} required`}
          onClick={() => onNavigate({ name: "collection-metadata", collectionId })}
        />
        <StatChip
          label="Indexed vectors"
          value={vectorCount !== undefined ? vectorCount.toLocaleString() : "…"}
          sub={docs ? `across ${enabledDocs} enabled doc${enabledDocs === 1 ? "" : "s"}` : undefined}
          onClick={() => onNavigate({ name: "collection-search", collectionId })}
        />
        <StatChip
          label="Formats"
          value={collection.supported_formats.length}
          sub={collection.supported_formats.join(", ")}
          onClick={() => onNavigate({ name: "collection-pipeline", collectionId })}
        />
        <StatChip
          label="Max file"
          value={`${maxSizeMb} MB`}
          sub="per upload"
          onClick={() => onNavigate({ name: "collection-edit", collectionId })}
        />
        <StatChip
          label="Job timeout"
          value={
            <span style={{ fontFamily: t.font.mono }}>
              {collection.job_timeout_seconds !== null ? `${collection.job_timeout_seconds}s` : "default"}
            </span>
          }
          sub="whole-ingest-job wall-clock budget"
          onClick={() => onNavigate({ name: "collection-edit", collectionId })}
        />
      </div>
    </>
  );
}
