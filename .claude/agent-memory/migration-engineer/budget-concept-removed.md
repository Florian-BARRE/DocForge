---
name: budget-concept-removed
description: The budget concept was fully removed; migration 013 drops its columns. What was kept vs dropped from Brique D.
metadata:
  type: project
---

The budget concept (per-collection spend cap + per-job spend accumulator) was removed from the
DocForge models/code and its DB columns were dropped in migration `013_drop_budget_columns.py`
(down_revision 012).

**Dropped columns:**
- `collection.budget_cap_usd` — `Float`, nullable. Originally added in `010_collection_limits`
  (Brique D, per-collection cumulative-spend cap; NULL = uncapped).
- `job.budget_spent` — `Float`, NOT NULL, server_default `'0.0'`. Originally in `001_initial_schema`
  (per-job cumulative spend accumulator).

**KEPT (do NOT confuse with budget):** `collection.max_in_flight` (`Integer`, nullable) — the OTHER
Brique D limit column from 010. It is still used by the resource-admission gate. Only the budget
half of Brique D's limits was removed; the in-flight cap stays.

**Why this matters / how to apply:** If a future task touches Brique D limits or the
`/collections/{id}/limits` API, remember budget is gone — limits are now max_in_flight-only at the
DB level. As of the 013 work, downstream API-client artifacts still referenced `budget_cap_usd`
(`src/mcp/libs/sdk/limits.py`, `src/mcp/libs/tools/limits.py`, frontend `api/types.ts` +
`generated.ts`) — those are outside schema scope but a sign the limits API surface may need the
same cleanup. The backend router/repo and the SQLAlchemy models were already clean. See
[[migration-chain-conventions]].
