// ====== Code Summary ======
// Mirrors the backend's one-combined-call rule for the embed stage: when the dense and sparse slots
// both use `bge_server` on the same `base_url`, a single request produces both vectors.

import type { ProviderSlotView } from "../../../api/types";

const COMBINED_KIND = "bge_server";

export function isCombinedCall(slots: ProviderSlotView[]): boolean {
  const dense = slots.find((s) => s.slot === "dense");
  const sparse = slots.find((s) => s.slot === "sparse");
  if (!dense || !sparse) return false;
  if (dense.provider !== COMBINED_KIND || sparse.provider !== COMBINED_KIND) return false;
  const denseUrl = dense.config?.base_url;
  return typeof denseUrl === "string" && denseUrl !== "" && denseUrl === sparse.config?.base_url;
}
