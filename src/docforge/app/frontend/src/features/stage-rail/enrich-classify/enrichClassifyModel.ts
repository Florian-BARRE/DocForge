// ====== Code Summary ======
// Pure logic + display data for the bespoke enrich-classify panel. It maps the flat FigureClassifyConfig
// dict (figure_enrich_mode / classify_backend / use_heuristics / thresholds / VLM connection) onto the
// three human choices the panel presents, and mirrors the backend's figure_routing table so the panel can
// show each class → its enrichment branch. NO JSX, NO network — just readers, the method mapping, and the
// routing display constant.

export type EnrichMode = "classified" | "ocr_only";
/** The single human choice that stands in for the (classify_backend, use_heuristics) pair. */
export type ClassifyMethod = "heuristics" | "vlm" | "vlm_heuristics";

/** One class → its downstream enrichment branch. MIRRORS shared_libs/public_models/ir/figure_routing.py
 *  (FIGURE_ROUTING) — a stable, tiny taxonomy; kept in sync by hand, order matches the enrich rail. */
export interface ClassRoute {
  kind: string;
  title: string;
  target: string;
}

export const CLASS_ROUTES: ClassRoute[] = [
  { kind: "scanned_text", title: "Scanned text", target: "OCR chain" },
  { kind: "chart", title: "Chart", target: "Vision model → table" },
  { kind: "diagram", title: "Diagram", target: "Vision model → text" },
  { kind: "photo", title: "Photo", target: "Vision model → caption" },
  { kind: "decorative", title: "Decorative", target: "Skipped (no cost)" },
];

// ---- readers (config values arrive as `unknown`) ----
export function readStr(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}
export function readNum(v: unknown, fallback: number): number {
  return typeof v === "number" && Number.isFinite(v) ? v : fallback;
}
export function readBool(v: unknown, fallback: boolean): boolean {
  return typeof v === "boolean" ? v : fallback;
}

export function deriveMode(config: Record<string, unknown>): EnrichMode {
  return readStr(config.figure_enrich_mode, "classified") === "ocr_only" ? "ocr_only" : "classified";
}

export function deriveMethod(config: Record<string, unknown>): ClassifyMethod {
  if (readStr(config.classify_backend, "vlm") === "local") return "heuristics";
  return readBool(config.use_heuristics, true) ? "vlm_heuristics" : "vlm";
}

/** True when the two geometric threshold rules apply (local always runs them; VLM only if opted in). */
export function heuristicsApply(method: ClassifyMethod): boolean {
  return method !== "vlm";
}

/** True when a hosted vision endpoint is used (so the connection fields are relevant). */
export function usesVlm(method: ClassifyMethod): boolean {
  return method !== "heuristics";
}

type Emit = (field: string, value: unknown) => void;

/** Apply a method choice back onto the flat config via the same per-field onChange the rail uses. */
export function applyMethod(method: ClassifyMethod, emit: Emit): void {
  // 1. Local backend = the fully-offline heuristic classifier (no endpoint).
  if (method === "heuristics") {
    emit("classify_backend", "local");
    return;
  }
  // 2. Both VLM variants share the hosted backend; use_heuristics decides the obvious-case fast-path.
  emit("classify_backend", "vlm");
  emit("use_heuristics", method === "vlm_heuristics");
}
