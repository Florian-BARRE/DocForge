// ====== Code Summary ======
// Derives one overall health verdict for a collection's Overview dashboard from its jobs and
// documents — a single synthetic signal a user can read at a glance instead of cross-referencing
// the jobs list and the document catalogue themselves.

import type { Collection } from "../../api/collections";
import type { DocumentListItem } from "../../api/explorer";
import type { JobStatus } from "../../api/jobs";
import type { ChipTone } from "../../components/Chip";

/** One rendered verdict — a tone for the headline Chip, its label, and one line of detail. */
export interface HealthVerdict {
  tone: ChipTone;
  label: string;
  detail: string;
}

/**
 * Compute the collection's overall health verdict.
 *
 * Priority (most severe wins): still gathering signals → checking; any failed job/document →
 * errors; a stale index or a document disabled from search → attention needed; jobs still
 * running/pending → indexing; otherwise healthy.
 *
 * @param collection - The collection, for its `needs_reindex` flag.
 * @param jobs - Ingestion jobs, or null while still loading (a failed fetch degrades to `[]`).
 * @param docs - Documents, or null while still loading.
 * @returns The verdict to render in the health banner.
 */
export function computeHealthVerdict(
  collection: Collection,
  jobs: JobStatus[] | null,
  docs: DocumentListItem[] | null,
): HealthVerdict {
  // 1. Nothing to judge yet — the document catalogue hasn't resolved.
  if (docs === null) {
    return { tone: "dim", label: "Checking…", detail: "Gathering collection health signals…" };
  }

  const failedJobs = jobs?.filter((j) => j.status === "failed").length ?? 0;
  const failedDocs = docs.filter((d) => d.status === "failed").length;
  const activeJobs = jobs?.filter((j) => j.status === "running" || j.status === "pending").length ?? 0;
  const disabledDocs = docs.filter((d) => !d.enabled).length;

  // 2. Errors take priority — something in the pipeline actually broke.
  if (failedJobs > 0 || failedDocs > 0) {
    const parts: string[] = [];
    if (failedJobs > 0) parts.push(`${failedJobs} job${failedJobs === 1 ? "" : "s"}`);
    if (failedDocs > 0) parts.push(`${failedDocs} document${failedDocs === 1 ? "" : "s"}`);
    return { tone: "error", label: "Errors", detail: `${parts.join(" and ")} failed — check Jobs for the cause.` };
  }

  // 3. A stale index or a document intentionally hidden from search both need a human look.
  if (collection.needs_reindex || disabledDocs > 0) {
    const parts: string[] = [];
    if (collection.needs_reindex) parts.push("a config change needs reindexing");
    if (disabledDocs > 0) parts.push(`${disabledDocs} document${disabledDocs === 1 ? "" : "s"} disabled from search`);
    return { tone: "warn", label: "Attention needed", detail: parts.join(" · ") };
  }

  // 4. Nothing wrong, but ingestion is still in flight.
  if (activeJobs > 0) {
    return { tone: "info", label: "Indexing…", detail: `${activeJobs} job${activeJobs === 1 ? "" : "s"} in progress.` };
  }

  // 5. Quiet and clean.
  return { tone: "ok", label: "Healthy", detail: "All documents are indexed and searchable." };
}
