// ====== Code Summary ======
// A slim strip of quick-glance stat chips below the provider health board — documents, metadata
// fields, indexed vectors, formats, and max file size, each a one-click jump to the tab that owns
// that detail. Deliberately NOT a card grid: the health board is the Overview's hero, this is a
// secondary summary.

import type { Collection, CollectionHealth, FieldSpec } from "../../api/collections";
import type { DocumentListItem } from "../../api/explorer";
import type { JobStatus } from "../../api/jobs";
import type { Navigate } from "../../shell/view";
import { theme as t } from "../../theme";
import { lastIngestLabel } from "./collectionHealth";
import { MetaLine, StatChip } from "./OverviewCardPrimitives";

interface OverviewStatStripProps {
  collection: Collection;
  docs: DocumentListItem[] | null;
  fields: FieldSpec[];
  health: CollectionHealth | null;
  /** This collection's own job history — null while unresolved. Drives the "Jobs" chip below;
   *  always carries `done/total` alongside the live `pending`/`running` counts so the chip still
   *  reads as informative once the backlog has drained to 0/0. */
  jobs: JobStatus[] | null;
  collectionId: string;
  onNavigate: Navigate;
}

export function OverviewStatStrip({ collection, docs, fields, health, jobs, collectionId, onNavigate }: OverviewStatStripProps) {
  const enabledDocs = docs?.filter((d) => d.enabled).length ?? 0;
  const requiredFields = fields.filter((f) => f.required).length;
  const maxSizeMb = (collection.max_file_size_bytes / (1024 * 1024)).toFixed(1);
  const vectorCount = health?.search.index.vector_count;
  const pendingJobs = jobs?.filter((j) => j.status === "pending").length ?? 0;
  const runningJobs = jobs?.filter((j) => j.status === "running").length ?? 0;
  const doneJobs = jobs?.filter((j) => j.status === "done").length ?? 0;

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
          label="Jobs"
          value={jobs ? jobs.length.toLocaleString() : "…"}
          sub={jobs ? `${pendingJobs} pending · ${runningJobs} running · ${doneJobs}/${jobs.length} done` : undefined}
          onClick={() => onNavigate({ name: "collection-jobs", collectionId })}
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
            // Only the machine value (a duration) is mono per brand.md — "default" is prose, not a
            // number, and reads in the app's normal Archivo voice like everywhere else.
            collection.job_timeout_seconds !== null
              ? <span style={{ fontFamily: t.font.mono }}>{collection.job_timeout_seconds}s</span>
              : "default"
          }
          sub="whole-ingest-job wall-clock budget"
          onClick={() => onNavigate({ name: "collection-edit", collectionId })}
        />
      </div>
    </>
  );
}
