// ====== Code Summary ======
// The set of node `kind`s the "parser" family can register, mirrored from the backend so the
// Layout tab can single out parser-family provenance rows without a palette fetch (the document
// explorer doesn't otherwise load `GET /pipelines/ingest` — see LayoutTab.tsx's parseChain memo).
//
// MUST stay in sync with `shared/libs/pipelines/ingest/nodes/parse/parser/` (one subfolder per
// kind, each core.py declaring `KIND = "…"`) — currently docling, granite_docling, pp_structure.
// A new parser brick lands there first; add its kind here in the same change. If this ever drifts
// out of sync the only symptom is a missing/extra pill in the parse-chain trace (cosmetic), never
// a build/runtime failure — but it should still be kept honest.

export const PARSER_KINDS = new Set(["docling", "granite_docling", "pp_structure"]);
