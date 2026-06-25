---
name: deletion-batch-residue
description: On large feature-purge batches, identifier-grep misses orphaned env vars + stale docstrings — check both explicitly
metadata:
  type: feedback
---

When reviewing a "delete the whole concept, no legacy" batch (e.g. the 2026-06-25 budget purge: 69 files removing every budget/cost field), grepping the removed symbol names finds zero hits yet residue still survives in two predictable blind spots that DON'T match those names:

1. **Orphaned env vars in `BaseRuntimeConfig`** (`common/base_config/runtime/base_config.py`) and `services/docforge/.env*`. A removed feature's enforcement is deleted but the `env("X")` line that fed it remains, read nowhere. Crashes nothing (env has a default) but is exactly the "legacy" the user wants gone. Budget example: `ENRICH_MAX_BUDGET_USD` survived.
2. **Stale docstrings** describing return tuples / fields that no longer exist (e.g. `EngineResult ... + budget spent`, chain trace tuple `(…, cost)`). Cosmetic, never caught by symbol-grep.

**Why:** the user mandate was "supprime tout, pas de legacy" — residue that doesn't crash still violates it, and these two categories are invisible to the obvious grep.

**How to apply:** after the removed-identifier grep comes back clean, run a SECOND case-insensitive grep on the *feature word* (e.g. `budget`/`cost`) across `base_config`, `services/*.env*`, and docstrings — then manually separate true hits from legitimately-named survivors (here: the unrelated `TokenBudget` chunking split-method dominated the noise).

**Also distinguish in-scope vs out-of-scope survivors:** an internal column threaded consistently end-to-end with a hardcoded sentinel (budget batch: `provider_call.cost` column always set to `0.0`, not in the migration's drop scope) is NOT a dangler — it doesn't crash and was deliberately excluded. Flag it as a follow-up, do not block the batch on it. Related: [[extra_ignore_provider_field_removal]], [[deployment_knob_privateattr]].
