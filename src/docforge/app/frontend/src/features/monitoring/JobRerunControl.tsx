// ====== Code Summary ======
// The quick re-run control for one job — reruns the stored document through the collection's
// current pipeline and jumps straight to the freshly created job (same reingestDocument→navigate
// pattern as DocumentPageActions/CorpusRowActions). Prominent (primary) once the job has FAILED —
// that's the main reason to reach for this from the job detail page; still available, but
// secondary, once the job is done/cancelled. Renders nothing while the job is still
// pending/running — there is nothing to re-run yet, and a concurrent reingest is refused anyway.
//
// Two distinct actions, both explicit in their own label ("Re-run (cached)" / "Force (no cache)")
// so a user scanning the row never has to guess which one recomputes everything: "Re-run" fires
// immediately (cheap, reuses the per-stage cache — a persona was confused it needed explaining, see
// round-4 T10); "Force" is the expensive one (recomputes every stage from scratch, no cache) and
// goes through the SAME inline two-step confirm as JobCancelControl's own Force action, after a
// persona accidentally triggered a real reingest by clicking it without warning.

import { useState } from "react";
import { reingestDocument } from "../../api/documents";
import { HttpError } from "../../api/http";
import type { JobStatus } from "../../api/jobs";
import { Button } from "../../components/Button";
import { useToast } from "../../shell/toast";
import type { Navigate } from "../../shell/view";
import { theme } from "../../theme";

interface JobRerunControlProps {
  job: JobStatus;
  collectionId: string;
  onNavigate: Navigate;
}

const RERUNNABLE = new Set(["done", "failed", "cancelled"]);

export function JobRerunControl({ job, collectionId, onNavigate }: JobRerunControlProps) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [confirmingForce, setConfirmingForce] = useState(false);

  if (!RERUNNABLE.has(job.status)) return null;

  const fire = async (force: boolean) => {
    setBusy(true);
    try {
      const { job_id } = await reingestDocument(job.document_id, { force });
      toast.success(force ? "Force re-run started (no cache)" : "Re-run started");
      onNavigate({ name: "job", collectionId, jobId: job_id });
    } catch (e) {
      if (e instanceof HttpError && e.status === 409) {
        toast.info("A run is already active for this document.");
      } else if (e instanceof HttpError && e.status === 403) {
        // A read-scoped key can view the job but can't mint a new one — surface it plainly
        // instead of letting the control silently no-op or crash.
        toast.error("This API key can't start a re-run (read-only scope).");
      } else {
        toast.error(e instanceof HttpError ? e.message : String(e));
      }
      setBusy(false);
      setConfirmingForce(false);
    }
  };

  const failed = job.status === "failed";

  if (confirmingForce) {
    return (
      <span style={{ display: "inline-flex", alignItems: "center", gap: theme.space.xs }}>
        <span style={{ color: theme.color.error, fontSize: theme.font.size.xs }}>
          Recompute every stage from scratch, no cache — costly. Force re-run?
        </span>
        <Button variant="danger" size="sm" disabled={busy} onClick={() => fire(true)}>
          {busy ? "…" : "Confirm"}
        </Button>
        <Button variant="ghost" size="sm" disabled={busy} onClick={() => setConfirmingForce(false)}>Back</Button>
      </span>
    );
  }

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: theme.space.xs }}>
      <Button
        variant={failed ? "primary" : "secondary"}
        size="sm"
        disabled={busy}
        onClick={() => fire(false)}
        title="Reruns the pipeline, reusing any already-computed stage cache — fast and cheap."
      >
        {busy ? "…" : "Re-run (cached)"}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        disabled={busy}
        onClick={() => setConfirmingForce(true)}
        title="Bypass the stage cache and recompute every stage from scratch."
      >
        Force (no cache)
      </Button>
    </span>
  );
}
