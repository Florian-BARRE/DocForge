---
name: reindex-staleness-coherence
description: How reindex_diff is shared between config version-bump and per-document staleness, and the fragile transient _reindex_reasons attr
metadata:
  type: project
---

`ConfigRepoHelpers.reindex_diff` is the SINGLE source of truth for "does this config change invalidate indexed docs". It is called from TWO places with old/new in opposite roles:

- `ConfigRepository.apply_config` — old=collection (ORM), new=patch (dicts). Drives version bump + `needs_reindex`.
- `DocumentStaleness.evaluate` (`app/backend/routers/collections/documents/staleness.py`) — old=snapshot config (dicts), new=collection (ORM). Drives per-doc `stale` flag.

**Why:** the prompt asked whether these two share a definition — they DO, intentionally. The boolean verdict is symmetric; only the reason-strings are direction-sensitive ("ajouté"/"retiré"), which is correct for each caller's narrative. Do NOT flag this as a divergence. `_attr` handles both ORM and dict inputs, so the mixed-type calls are safe.

**Key rule encoded in reindex_diff:** `search` pipeline section is EXCLUDED from the indexing diff (query-time only). Only embedding model, non-`search` pipeline sections, and searchable (semantic/lexical) metadata fields trigger reindex/staleness.

**How to apply:** when reviewing config or staleness changes, confirm `search` stays excluded and both callers keep using the shared helper. If someone adds a new query-time pipeline section, it must also be excluded.

**Fragile spot — transient `_reindex_reasons`:** `apply_config` smuggles `reindex_reasons` onto the reloaded ORM instance as a plain attribute (`collection._reindex_reasons = ...`), read by `app/backend/routers/collections/config/router.py` via `getattr`. Works only because the same in-memory instance flows back before session close. Flag any refactor that re-fetches the collection or changes `expire_on_commit` — it would silently drop the reasons (explainer falls back to generic "config d'indexation modifiée"). Better long-term: return `(collection, reasons)` tuple.
