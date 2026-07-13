---
name: colbert-late-interaction-review
description: Review heuristics for the ColBERT third-vector late-interaction feature — filter placement, off-path identity, colbert_dim derivation, flag-as-vector-presence proxy gap
metadata:
  type: project
---

# ColBERT late-interaction (`content_colbert`) — review heuristics

Feature: a 3rd Qdrant named vector `content_colbert` (multivector, MAX_SIM, int8, on_disk) for a
flag-gated late-interaction re-score. Built across bge_server + rework in parallel. Reviewed 2026-07-13,
verdict APPROVED (findings were LOW/non-blocking). Keep these as the reusable review lenses.

## What the correct implementation looks like (validate future changes against this)

- **Disabled-chunk filter on the INNER prefetch.** `QdrantSearchApi.hybrid`: when `colbert` given, the
  RRF fusion is a NESTED `models.Prefetch(prefetch=[branches...], query=FusionQuery(RRF), limit=pool)`
  and the outer `query_points(query=colbert, using=CONTENT_COLBERT)` re-scores the pool. The payload
  filter (`enabled=True` + disabled-doc `must_not`) lives on each INNER branch, so a disabled chunk
  never enters the pool and re-scoring can never resurrect it. A re-score that filters only on the outer
  query would be a correctness+security bug (see [[stale-scoped-tab-bypasses-gate]] mindset).
- **Off-path byte-identity.** `colbert is None` must reproduce the pre-change single-stage query
  verbatim. Verified by diff: the else-branch (`query_points(prefetch=branches, query=FusionQuery(RRF))`)
  is byte-identical to before; the two new params default to None/100. This is the highest-risk
  regression — always diff the None path, don't just trust green tests.
- **Metadata isolation.** colbert rides in `QdrantPoint.multivector` (a DEDICATED field, dense NOT
  overloaded). Translator sets `multivector={CONTENT_COLBERT: item.colbert}` on the CONTENT point only,
  never on `meta_<slug>_dense`. `index_api.update_vectors` (metagen post-hoc) builds only from
  `point.dense`+`point.sparse` — structurally cannot touch multivector. Confirm both on any change.
- **Dense-only provider degrades gracefully.** `openai_compatible` doesn't override `_wants_colbert`
  (base returns False) and has no `embed_colbert` config. So late-interaction request → `wants_colbert()`
  False → router sets `debug_info.late_interaction_skipped`, no 500. Config flag is the single source of
  truth mirrored on both ingest and query sides.

## LOW findings kept as watch-items (were not blocking)

- **`colbert_dim` derived from the FIRST chunk only.** `node.py`:
  `colbert_dim = len(colbert_vectors[0][0]) if colbert_vectors and colbert_vectors[0] else None`.
  If the first enabled chunk yields an empty token matrix (`[]`), colbert_dim is None while LATER chunks
  still carry colbert vectors → translator's `out.colbert_dim=None` → `collection_api.ensure` skips
  declaring `content_colbert` → the subsequent `upsert` of a point whose `multivector` names
  `content_colbert` FAILS the whole ingest job (loud, not silent). Dense doesn't have this (fixed 1024,
  never empty); colbert token count is variable. Fix shape: derive from the first NON-EMPTY entry.
- **Flag is a proxy for vector-presence, not a guarantee.** The graceful guard keys off the config flag
  (`wants_colbert()`), not actual Qdrant vector presence. Breaks in the ONE-WAY-DOOR misuse window:
  operator flips `embed_colbert=True` on an EXISTING collection without drop+recreate. `ensure` is
  idempotent → won't add `content_colbert` to the live collection → re-embed upsert fails; and a
  late-interaction search issues `using=content_colbert` against a schema lacking it → Qdrant error →
  500 (the guard says True). Documented one-way-door (drop+re-embed by design), so LOW — but there's no
  clear operator-facing message; it surfaces as a generic upsert/query error. Hardening: detect
  flag-on-but-vector-absent and emit a clear signal (or make the guard check real presence).

## Cross-agent seam checks that came back CLEAN (do them again on parallel builds)

- `grep -rn "getattr.*colbert\|hasattr.*colbert"` → none. The translator uses direct
  `bundle.embeddings.colbert_dim` (the field exists on `embed.py`), no defensive getattr bridge left
  over from parallel work. On any parallel multi-agent build, grep for stale getattr/hasattr bridges
  where one agent guarded against a field another agent was still adding.
