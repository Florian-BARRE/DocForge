// ====== Code Summary ======
// Loads the deployment's per-slot provider availability (`embed_dense` / `embed_sparse` of GET
// /capabilities) once, so a slot picker can grey out kinds this deployment cannot serve. A failed
// or pending fetch yields `null` = "unknown" — nothing is greyed on a guess.

import { useEffect, useState } from "react";
import { getCapabilities, type CapabilityMatrix } from "../../../api/capabilities";

export type SlotCapabilities = Pick<CapabilityMatrix, "embed_dense" | "embed_sparse">;

export function useSlotCapabilities(): SlotCapabilities | null {
  const [capabilities, setCapabilities] = useState<SlotCapabilities | null>(null);
  useEffect(() => {
    let cancelled = false;
    getCapabilities()
      .then((response) => {
        if (!cancelled) setCapabilities(response.capabilities);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  return capabilities;
}

/** The kinds this deployment offers for `slot`, or `null` when unknown (or the slot is not an embed slot). */
export function deployedKindsFor(capabilities: SlotCapabilities | null, slot: string): string[] | null {
  if (!capabilities) return null;
  if (slot === "dense") return capabilities.embed_dense ?? null;
  if (slot === "sparse") return capabilities.embed_sparse ?? null;
  return null;
}
