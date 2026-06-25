---
name: embed-providers-and-tei-alias
description: Embed provider choices are bge_server + openai_compat only; legacy "tei" id is a back-compat alias to bge_server (not a registered choice)
metadata:
  type: project
---

Embed provider CHOICES are `bge_server` + `openai_compat` only. The legacy `tei` choice was removed.

**Why:** `bge_server` (src/bge_server, local BGE-M3 host) replaced the off-the-shelf TEI image and speaks the same TEI HTTP contract. `BgeServerEmbedConfig.build()` still instantiates the shared HTTP client `TeiEmbedProvider` (`providers/embed/tei/provider.py`) — the *client* stays; only the duplicate *config choice* was dropped.

**How to apply:**
- `TeiEmbedConfig` (`providers/embed/tei/config.py`) is KEPT but NO LONGER `@register("embed")` → absent from discovery + the `EmbedProviderConfig` discriminated union. Do not re-register it.
- `TeiEmbedProvider` (the HTTP client) must stay intact — it is the shared embed client reused by bge_server. Never delete it.
- Default empty embed chain → `BgeServerEmbedConfig` (set in `EmbedConfig._validate_and_default_embed_chain` and `build_default_pipeline` in `config/pipeline/pipeline.py`).
- **Legacy alias compat:** stored pipelines with `embed.chain[*].id == "tei"` (or `embed.sparse.id == "tei"`) are rewritten to `"bge_server"` BEFORE the discriminated-union dispatch via `EmbedConfig._compat` (mode="before") using `_LEGACY_EMBED_ID_ALIASES = {"tei": "bge_server"}`. Compatible fields (base_url/api_key/model/batch_size/embed_sparse/locality) carry over; bge_server's extra `timeout_s` falls back to its default 180. Same alias rewrite also lives in `s4_chunk/config/semantic.py::SemanticConfig._compat` (its embed sub-config) — keep them consistent.
- To collapse another removed embed id into a current one, add it to `_LEGACY_EMBED_ID_ALIASES` rather than re-adding the config to the union.

**Follow-up noted (NOT done):** the same legacy-TEI duplication likely exists for the RERANK provider (`providers/rerank/bge` vs `providers/rerank/bge_server`) — out of scope for the embed change; verify before assuming.
