// ====== Code Summary ======
// The Overview's headline — a status Chip plus one line of text summarizing collection health,
// computed from job and document signals so the state is legible without opening Jobs or the
// document explorer.

import type { Collection } from "../../api/collections";
import type { DocumentListItem } from "../../api/explorer";
import type { JobStatus } from "../../api/jobs";
import { Chip } from "../../components/Chip";
import { theme as t } from "../../theme";
import { computeHealthVerdict } from "./collectionHealth";

interface HealthBannerProps {
  collection: Collection;
  jobs: JobStatus[] | null;
  docs: DocumentListItem[] | null;
}

export function HealthBanner({ collection, jobs, docs }: HealthBannerProps) {
  const verdict = computeHealthVerdict(collection, jobs, docs);
  return (
    <div
      style={{
        display: "flex", alignItems: "center", gap: t.space.m,
        background: t.color.surface, border: `1px solid ${t.color.line}`, borderRadius: t.radius.l,
        padding: `${t.space.m}px ${t.space.l}px`, boxShadow: t.shadow.sm, marginBottom: t.space.l,
      }}
    >
      <Chip tone={verdict.tone}>{verdict.label}</Chip>
      <span style={{ color: t.color.text, fontSize: t.font.size.l }}>{verdict.detail}</span>
    </div>
  );
}
