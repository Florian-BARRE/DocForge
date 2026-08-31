// ====== Code Summary ======
// The stop/cancel control for one job — inline two-step confirm (no modal), same shape as
// CorpusRowActions' delete confirm. Renders nothing once the job is terminal. Labels "Cancel" on a
// queued job, "Stop" on a running one (cooperative, force=false); a running job also gets a
// separate danger "Force" action (force=true) for a wedged/looping job. Stop is neutral/steel —
// forge orange stays reserved for the job's own "running" state, never this control. While a
// cooperative stop is pending (`cancel_requested`) the Stop button is replaced by a "stopping…"
// indicator so the user isn't tempted to spam it; Force stays available as the escape hatch.

import { useState } from "react";
import { cancelJob, getJob, type JobStatus } from "../../api/jobs";
import { Button } from "../../components/Button";
import { Chip } from "../../components/Chip";
import { HttpError } from "../../api/http";
import { useToast } from "../../shell/toast";
import { theme } from "../../theme";

interface JobCancelControlProps {
  job: JobStatus;
  /** Applied immediately on a successful call (or a full refresh after a 409) so the row/page
   *  reflects the new state without waiting for the next poll/stream tick. */
  onUpdated: (patch: Partial<JobStatus>) => void;
}

type ConfirmMode = "stop" | "force" | null;

export function JobCancelControl({ job, onUpdated }: JobCancelControlProps) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState<ConfirmMode>(null);

  const cancellable = job.status === "pending" || job.status === "running";
  if (!cancellable) return null;

  const isQueued = job.status === "pending";
  const stopping = job.status === "running" && job.cancel_requested;

  const fire = async (force: boolean) => {
    setBusy(true);
    try {
      const result = await cancelJob(job.job_id, force);
      onUpdated({ status: result.status, cancel_requested: result.cancel_requested });
      toast.success(
        result.outcome === "cancelled"
          ? "Job cancelled."
          : "Stop requested — it will halt at its next stage boundary.",
      );
    } catch (e) {
      if (e instanceof HttpError && e.status === 409) {
        toast.info("That job already finished — refreshing its status.");
        try {
          onUpdated(await getJob(job.job_id));
        } catch {
          // Best effort — the next poll/stream tick will reconcile it anyway.
        }
      } else {
        toast.error(e instanceof HttpError ? e.message : String(e));
      }
    } finally {
      setBusy(false);
      setConfirm(null);
    }
  };

  if (confirm) {
    const forcing = confirm === "force";
    return (
      <span onClick={(e) => e.stopPropagation()} style={{ display: "inline-flex", alignItems: "center", gap: theme.space.xs }}>
        <span style={{ color: forcing ? theme.color.error : theme.color.dim, fontSize: theme.font.size.xs }}>
          {forcing ? "Force stop now?" : isQueued ? "Cancel this job?" : "Stop at the next stage boundary?"}
        </span>
        <Button variant={forcing ? "danger" : "secondary"} size="sm" disabled={busy} onClick={() => fire(forcing)}>
          {busy ? "…" : "Confirm"}
        </Button>
        <Button variant="ghost" size="sm" disabled={busy} onClick={() => setConfirm(null)}>Back</Button>
      </span>
    );
  }

  return (
    <span onClick={(e) => e.stopPropagation()} style={{ display: "inline-flex", alignItems: "center", gap: theme.space.xs }}>
      {stopping ? (
        <Chip tone="skip" title="A cooperative stop was requested — it will halt at its next stage boundary.">
          stopping…
        </Chip>
      ) : (
        <Button variant="secondary" size="sm" onClick={() => setConfirm("stop")}>
          {isQueued ? "Cancel" : "Stop"}
        </Button>
      )}
      {job.status === "running" && (
        <Button
          variant="danger"
          size="sm"
          onClick={() => setConfirm("force")}
          title="Terminate immediately, without waiting for a safe stage boundary — for a wedged or looping job."
        >
          Force
        </Button>
      )}
    </span>
  );
}
