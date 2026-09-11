// ====== Code Summary ======
// Drives one dry-run preview run: submit -> poll -> settle. Async-worker-side by construction (see
// api/preview.ts's doc comment for why — covers every pipeline, including docling). A run always
// carries the CALLER's current candidate blob as the override, so "test on a sample" always reflects
// exactly what's on screen (saved or not) — the whole point of an in-editor dry-run. Guards against
// setting state after unmount / after a newer run superseded an older poll loop (`runIdRef`).

import { useCallback, useEffect, useRef, useState } from "react";
import { getPreviewJob, submitPreviewJob, type PreviewResponse } from "../../../api/preview";
import type { GroupBlob } from "../../../api/types";

const POLL_INTERVAL_MS = 1200;

export type PreviewRunStatus = "idle" | "submitting" | "pending" | "running" | "done" | "failed";

export type PreviewSource = { kind: "document"; documentId: string } | { kind: "upload"; file: File };

interface UsePipelinePreviewArgs {
  collectionId: string;
  blob: GroupBlob;
}

export function usePipelinePreview({ collectionId, blob }: UsePipelinePreviewArgs) {
  const [status, setStatus] = useState<PreviewRunStatus>("idle");
  const [result, setResult] = useState<PreviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const blobRef = useRef(blob);
  blobRef.current = blob;
  const pollTimeoutRef = useRef<number>();
  // Bumped on every `run()` / unmount — a poll whose runId no longer matches the latest is a stale
  // in-flight response from a superseded/abandoned run and must not touch state.
  const runIdRef = useRef(0);

  useEffect(() => () => {
    runIdRef.current += 1;
    window.clearTimeout(pollTimeoutRef.current);
  }, []);

  const poll = useCallback((previewId: string, runId: number) => {
    getPreviewJob(collectionId, previewId)
      .then((job) => {
        if (runIdRef.current !== runId) return;
        if (job.status === "pending" || job.status === "running") {
          setStatus(job.status);
          pollTimeoutRef.current = window.setTimeout(() => poll(previewId, runId), POLL_INTERVAL_MS);
          return;
        }
        if (job.status === "done") {
          setStatus("done");
          setResult(job.result);
          return;
        }
        setStatus("failed");
        setError(job.error ?? "The preview job failed to run.");
      })
      .catch((e) => {
        if (runIdRef.current !== runId) return;
        setStatus("failed");
        setError(e instanceof Error ? e.message : String(e));
      });
  }, [collectionId]);

  const run = useCallback((source: PreviewSource) => {
    window.clearTimeout(pollTimeoutRef.current);
    const runId = (runIdRef.current += 1);
    setStatus("submitting");
    setResult(null);
    setError(null);
    const submission = source.kind === "document"
      ? { collectionId, documentId: source.documentId, blob: blobRef.current }
      : { collectionId, file: source.file, blob: blobRef.current };
    submitPreviewJob(submission)
      .then(({ preview_id }) => {
        if (runIdRef.current !== runId) return;
        setStatus("pending");
        poll(preview_id, runId);
      })
      .catch((e) => {
        if (runIdRef.current !== runId) return;
        setStatus("failed");
        setError(e instanceof Error ? e.message : String(e));
      });
  }, [collectionId, poll]);

  const reset = useCallback(() => {
    runIdRef.current += 1;
    window.clearTimeout(pollTimeoutRef.current);
    setStatus("idle");
    setResult(null);
    setError(null);
  }, []);

  return { status, result, error, run, reset };
}
