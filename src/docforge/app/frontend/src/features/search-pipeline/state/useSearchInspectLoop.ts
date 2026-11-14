// ====== Code Summary ======
// The verify loop of the search pipeline editor: the debounced `/inspect` of the local draft, its
// verdict (valid + issues), the in-flight/abort bookkeeping and the armed-but-not-yet-sent window
// (`debouncePending`) that blocks Save. Extracted from useSearchPipelineEditor.

import { useCallback, useEffect, useRef, useState, type MutableRefObject } from "react";
import { issuesFromBuildError } from "../../../api/http";
import { inspect } from "../../../api/pipelines";
import type { GroupBlob, ValidationIssue } from "../../../api/types";

const DEBOUNCE_MS = 400;

export function useSearchInspectLoop(
  inspectUrl: string | null,
  blobLatestRef: MutableRefObject<GroupBlob | null>,
) {
  const [valid, setValid] = useState(true);
  const [issues, setIssues] = useState<ValidationIssue[]>([]);
  const [checking, setChecking] = useState(false);
  const [debouncePending, setDebouncePending] = useState(false);
  const inspectUrlRef = useRef<string | null>(null);
  inspectUrlRef.current = inspectUrl;
  const abortRef = useRef<AbortController | undefined>(undefined);
  const debounceRef = useRef<number | undefined>(undefined);

  const runInspect = useCallback((target: GroupBlob) => {
    const url = inspectUrlRef.current;
    if (!url) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setChecking(true);
    inspect(url, target, controller.signal)
      .then((result) => {
        if (blobLatestRef.current !== target) return; // a newer edit already superseded this check
        setValid(result.valid);
        setIssues(result.build_error ? issuesFromBuildError(result.build_error) : result.issues);
      })
      .catch((error) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        if (blobLatestRef.current !== target) return; // a newer edit already superseded this check
        // A transient background verify blip must NOT tear down the editor (that would drop the
        // user's unsaved edits). Keep the draft mounted, mark it unverified (blocks Save) and show
        // the reason inline — a successful re-verify on the next keystroke clears it.
        setValid(false);
        setIssues([{
          code: "verify_failed",
          location: "inspect",
          message: error instanceof Error ? error.message : String(error),
        }]);
      })
      .finally(() => setChecking(false));
  }, [blobLatestRef]);

  // Tear down a pending debounce + any in-flight verify on unmount (the runtime path has no
  // per-render cleanup of its own, unlike the cancelled-flag guard on the initial load).
  useEffect(() => () => {
    window.clearTimeout(debounceRef.current);
    abortRef.current?.abort();
  }, []);

  /** Seed the verdict from the initial load's `/inspect`. */
  const seedVerdict = useCallback((nextValid: boolean, nextIssues: ValidationIssue[]) => {
    setValid(nextValid);
    setIssues(nextIssues);
  }, []);

  /** Typing: arm a debounced `/inspect` of the latest draft (re-arming resets the window). */
  const verifyDebounced = useCallback(() => {
    window.clearTimeout(debounceRef.current);
    setDebouncePending(true);
    debounceRef.current = window.setTimeout(() => {
      setDebouncePending(false);
      const settled = blobLatestRef.current;
      if (settled) runInspect(settled);
    }, DEBOUNCE_MS);
  }, [blobLatestRef, runInspect]);

  /** A discrete edit: drop any armed debounce and verify `target` immediately. */
  const verifyNow = useCallback((target: GroupBlob) => {
    window.clearTimeout(debounceRef.current);
    setDebouncePending(false);
    runInspect(target);
  }, [runInspect]);

  /** Drop the armed debounce timer (the Reset path) without touching the pending flag. */
  const cancelDebounce = useCallback(() => window.clearTimeout(debounceRef.current), []);

  return { valid, issues, checking, debouncePending, seedVerdict, verifyDebounced, verifyNow, cancelDebounce };
}
