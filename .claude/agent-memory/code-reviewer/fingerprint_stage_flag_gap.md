---
name: fingerprint-stage-flag-gap
description: v2 flow node-cache — a stage-level config flag (not a chain field) is silently dropped from the Merkle fingerprint, serving a stale cached stage output
metadata:
  type: project
---

# Node-cache fingerprint: stage-level flags dropped from the Merkle key

In the v2 flow node-engine (`worker/libs/pipeline/run/fingerprint.py`), a NODE_CACHED stage's
fingerprint folds ONLY: stage id + `_CODE_VERSION` + `node.fingerprint_params()` + the resolved
provider-chain `signature()`s (enrich: classifier/ocr/vlm) + upstream fingerprints. Any stage knob
that is NOT a chain field AND NOT surfaced via `fingerprint_params()` is INVISIBLE to the cache key.

**Confirmed gap (Phase B.5/D, 2026-06-30):** `EnrichStage(chart_to_data=…)` drives
`EnrichRouting.decide(kind, ocr_enabled, vlm_enabled, chart_to_data)` (classify.py) — it materially
changes whether CHART figures get chart-schema extraction. But `EnrichStage` has NO `fingerprint_params`
method, and `chart_to_data` is not part of any chain signature. So toggling `enrich.chart_to_data`
(with an already-configured vlm chain, so the vlm signature is unchanged) leaves `enrich_fp` unchanged
→ enrich node-cache HIT → stale enriched IR without chart data. Reindex does NOT help: same doc_id +
same fingerprint = still a hit. Fix shape: add `fingerprint_params(self) -> {"chart_to_data": ...}` to
EnrichStage (mirrors ParseStage.fingerprint_params which folds `[[parser_id, use_gpu], ...]`).

**Why:** ParseStage got this right (its parsers-as-nodes identity + use_gpu IS in fingerprint_params);
enrich's flat boolean was overlooked because ocr_enabled/vlm_enabled ARE implicitly captured (empty
chain → "" signature), creating a false sense that all enrich knobs are covered.

**How to apply:** when reviewing a NODE_CACHED stage (ingest/parse/enrich), enumerate every constructor
arg the stage takes. For EACH one ask "does swapping this value change the stage output?" If yes, it
MUST appear in either a chain signature or `fingerprint_params()`. Chain presence flags are covered for
free; standalone booleans/scalars (chart_to_data, future accept_threshold, batch sizes that affect
output) are the danger. A smoke test (cold→warm hit) will NOT catch this — only a config-toggle +
re-ingest of the same doc_id reveals it.

Related latent: `ParseStage` accept_threshold (0.8) is hardcoded in `build.py`, not in
`fingerprint_params` — fine while hardcoded, a gap the day it becomes per-collection. See
[[reindex_staleness_coherence]].
