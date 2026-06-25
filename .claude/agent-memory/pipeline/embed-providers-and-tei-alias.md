---
name: embed-providers-and-tei-alias
description: Embed + rerank provider choices = bge_server (+openai_compat/cohere_rerank); legacy "tei"/"bge_reranker" ids are back-compat aliases to bge_server
metadata:
  type: project
---

Both EMBED and RERANK collapsed their off-the-shelf-TEI duplicate into the local `bge_server` host.
- EMBED choices = `bge_server` + `openai_compat` only (legacy `tei` removed).
- RERANK choices = `bge_server` + `cohere_rerank` only (legacy `bge_reranker` removed).

**Why:** `bge_server` (src/bge_server, local BGE-M3 host) replaced the off-the-shelf TEI image for both embed and rerank and speaks the same TEI HTTP contract (`/embed` + `/rerank`). The bge_server configs' `build()` still instantiate the shared HTTP clients `TeiEmbedProvider` (`providers/embed/tei/provider.py`) and `BgeRerankProvider` (`providers/rerank/bge/provider.py`) — the *clients* stay; only the duplicate *config choices* were dropped.

**How to apply:**
- `TeiEmbedConfig` (`providers/embed/tei/config.py`) and `BgeRerankerConfig` (`providers/rerank/bge/config.py`) are KEPT but NO LONGER `@register(...)` → absent from discovery + their discriminated unions. Do not re-register them. Registry truth: `get_configs("embed")=={bge_server,openai_compat}`, `get_configs("rerank")=={bge_server,cohere_rerank}`.
- The HTTP clients (`TeiEmbedProvider`, `BgeRerankProvider`) must stay intact — shared clients reused by the bge_server configs. Never delete them.
- Default empty embed chain → `BgeServerEmbedConfig` (`EmbedConfig` after-validator + `build_default_pipeline`). Rerank chain is OPTIONAL (`rerank.enabled` default False) and is NEVER auto-filled — there is no rerank default-fill; only the legacy-id rewrite + union changed.
- **Legacy alias compat (shared helper):** `spec_utils.normalize_legacy_id(spec, aliases)` rewrites a spec's `id` BEFORE the discriminated-union dispatch. Per-site alias maps:
  - `EmbedConfig._compat` (mode="before"): `_LEGACY_EMBED_ID_ALIASES = {"tei": "bge_server"}` over `chain[*]` + `sparse`.
  - `SemanticConfig._compat` (`s4_chunk/config/semantic.py`): same embed map over its `embed` sub-config (+ legacy flat `base_url` lift -> `{id: bge_server}`).
  - `RerankConfig._compat` (mode="before", `config/pipeline/stages/search_config.py`): `_LEGACY_RERANK_ID_ALIASES = {"bge_reranker": "bge_server"}` over `chain[*]`.
  Compatible fields carry over; the replacement's extra field falls back to its default (embed bge_server adds `timeout_s=180`).
- To collapse another removed id, add it to the relevant alias map + drop the config from the union — do NOT re-add the config to the union.

**Infra follow-up (NOT done, out of scope):** the docker-compose `reranker` TEI service is now redundant (bge_server serves /rerank). Hand to `infra` before removing.
