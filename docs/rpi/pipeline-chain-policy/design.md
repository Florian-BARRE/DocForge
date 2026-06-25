# Design — Uniform pipeline stage model: Chain + Gate + Failure Policy

> Status: **DESIGN / FOR VALIDATION** (no code yet). Author: orchestrator, 2026-06-25.
> Goal: turn every fallible / model-requiring pipeline stage into ONE uniform contract so behavior
> is predictable, configurable per collection, and fully observable — replacing today's six
> different hardcoded reactions to the same failure signal.

---

## 1. The vision (user's words, formalized)

> "Chaque étape demandant un modèle quelconque ou qui peut échouer : on met une **chain**, on
> paramètre un **score** en dessous duquel on appelle le suivant (fallback), et on peut **choisir**
> une politique : **continue** (erreur ignorée) ou **raise** (stoppe la pipeline + erreur précise)."

So every such stage = **Chain of providers** + **Gate** (score/time/cost threshold → escalate to the
next provider) + **Failure Policy** (`continue` | `raise`) deciding what happens when the chain is
**exhausted** (no provider produced an acceptable result).

---

## 2. Current state (why this is needed)

The `Chain[T,R]` primitive already iterates providers and escalates on (a) provider error or
(b) result below `gate.min_score`. **But:**

- `Chain.call` **never raises** — on exhaustion it returns `ChainOutcome(result=None)` and the
  **caller decides**. Result: **6 different hardcoded reactions** to the same `result is None`:
  - **RAISE** (→ doc `failed`): S1 parse, S6 embed.
  - **CONTINUE / degrade**: S2 classifier (→ PHOTO fallback), S2 OCR (→ skip), S2 VLM (→ skip),
    search rerank (→ return pool un-reranked), query-transform (→ original query), S4 semantic
    embed (→ token-budget split).
- The raise-vs-continue choice is **hardcoded at every call-site** — not configurable.
- **`max_duration_ms` / `max_cost_usd` gates are dead** (parsed + shown in UI, never enforced).
- **rerank / query-transform / semantic-embed are NOT chains** — single provider + bespoke
  try/except, so they have no gate and no fallback at all.
- Inconsistencies: OCR gate default `0.85` vs `0.5` everywhere else; score means different things
  per provider family but shares one scalar threshold; empty-chain handling diverges (some builders
  raise `ProviderUnavailableError`, some return `None`); dead `ProviderChain`/`_PredicateGate`;
  silent **lossy** degradation (rerank returns results that *look* reranked but aren't, no signal).

(Full map: agent research 2026-06-25 — chain/core.py:113-156, chain_gate.py:50-73, the per-stage
call-sites listed in §6.)

---

## 3. The uniform contract

### 3.1 One object per fallible stage: `chain[] + gate`

Every fallible stage config carries:
```
chain: list[ProviderConfig]      # ordered: chain[0] primary, rest = fallbacks
gate:  ChainGateConfig           # the escalation + failure policy for THIS chain
```

### 3.2 `ChainGateConfig` (extended)

```python
class ChainGateConfig:
    min_score:       float = 0.5          # below → escalate to next provider   [WIRED today]
    max_duration_ms: int | None = None    # attempt slower than this → escalate  [TO WIRE]
    max_cost_usd:    float | None = None   # cumulative chain cost over this → stop escalating [TO WIRE]
    failure_policy:  Literal["raise", "continue"] = "raise"   # NEW — exhaustion behavior
    on_degraded:     Literal["best_effort", "empty"] = "empty" # NEW (continue only) — see 3.4
```

`failure_policy` lives on the **gate** because the gate is already the per-chain policy object:
serialized in the pipeline JSONB, already surfaced in discovery, already passed to the `Chain`.
Zero new plumbing for the stages that already have a gate (S1, S6, S2×3).

### 3.3 Escalation (unchanged in spirit, gates completed)

For each provider in order, run it → produce a `ChainAttempt {score, duration_ms, cost_usd,
succeeded, error}`. **Escalate to the next** when:
1. the provider **raised / returned None** (`succeeded=false`), OR
2. `score < min_score`, OR
3. `duration_ms > max_duration_ms` (NEW — too slow), OR
4. running `Σ cost_usd > max_cost_usd` (NEW — chain budget blown → stop trying more).

First provider that passes all gates → **accepted**, chain returns its result.

### 3.4 Exhaustion → Failure Policy (the new core)

When **no** provider is accepted (all raised / all below gates):

- **`raise`** → the chain raises `ChainExhaustedError(stage, attempts)` carrying a **precise**
  message: which stage, each provider tried, its score/error/duration. The worker's fail-closed
  boundary marks the document `failed` with that error. **Pipeline stops.**
- **`continue`** → the chain returns a degraded outcome; the pipeline **continues**. What "degraded"
  means is `on_degraded`:
  - `empty` (default): the stage gets `None` → its **degraded path** runs (OCR/VLM skipped, figure
    kept as-is, semantic-split → token-budget, rerank → retrieval order). Always records a
    **degradation event** (no more silent loss).
  - `best_effort`: if at least one provider **succeeded but was below threshold**, return the
    **highest-scoring** result anyway (use the imperfect result rather than nothing); only fall to
    `empty` if every provider hard-errored.

> **Key principle:** `continue` is only valid for stages that HAVE a degraded path. Stages that must
> produce output to proceed (parse, chunk, embed/index) only support `raise` (validated — see §4).

### 3.5 The Chain honors the policy (callers stop hand-rolling it)

`Chain.call(fn)` (or a thin `Chain.call_or_policy`) implements §3.4 itself:
- on exhaustion: `raise ChainExhaustedError` if `failure_policy=="raise"`, else return the
  degraded `ChainOutcome` (with `degraded=True`).
S1/S6 **drop** their hand-rolled `raise RuntimeError`; S2's bespoke None-handling becomes the
standard `continue` degraded path. **One reaction, configured — not six hardcoded.**

---

## 4. Per-stage application

| Stage | Becomes a chain? | Default policy | Allowed policies | Degraded path (when `continue`) |
|---|---|---|---|---|
| **S1 parse** | already | `raise` | raise only* | — (no doc without parse) |
| **S2 classifier** | already | `continue` | raise / continue | fallback kind = PHOTO, relevance 0 |
| **S2 OCR** | already | `continue` | raise / continue | skip OCR (no text) |
| **S2 VLM** | already | `continue` | raise / continue | skip VLM (no description/chart) |
| **S6 embed** | already | `raise` | raise only* | — (no index without vectors) |
| **search rerank** | **NEW chain** | `continue` | raise / continue | return retrieval order (flagged degraded) |
| **query transform** | **NEW chain** | `continue` | raise / continue | use original query |
| **S4 semantic embed** | **NEW chain** | `continue` | raise / continue | token-budget split |

\* "raise only": these stages can't meaningfully `continue` (the pipeline can't proceed without their
output). The config validator rejects `failure_policy=continue` on them (fail-fast, consistent with
the rerank-empty-chain rule). *Open question Q3 — could relax if you want "skip embedding, keep doc
parsed-only".*

---

## 5. Making the non-chain stages uniform

rerank / query-transform / semantic-embed are today single-provider + try/except. To join the model
they become `chain: list[...] + gate: ChainGateConfig` on the `Chain` primitive:
- **rerank**: `chain: [bge_server, cohere_rerank, …]` → real fallback (e.g. cohere → bge_server) +
  `continue` keeps today's behavior but **records degradation** instead of silently returning
  un-reranked results.
- **query-transform**: `chain: [llm provider, …]` → LLM fallback; `continue` = original query.
- **S4 semantic embed**: reuse the **same** `EmbedConfig` chain shape (kills the duplicate embed
  config surface flagged in the audit); `continue` = token-budget fallback.

This is the bigger lift (rebuild three bespoke stages on `Chain`), so it's a later sub-phase.

---

## 6. Inconsistencies fixed along the way

1. Remove dead `ProviderChain` / `_PredicateGate`.
2. Unify empty-chain handling: a chain builder always treats `chain: []` as "capability disabled"
   for `continue` stages, and raises `ProviderUnavailableError` only for `raise`-only stages.
3. Wire `max_duration_ms` / `max_cost_usd` in the gate (replaces the parallel S2-only budget path —
   `enrich.max_budget_usd` is reconciled with the gate cost cap; decide Q4).
4. Document score semantics per provider family in the UI (Docling block-ratio ≠ OCR confidence ≠
   VLM validity) so a single `min_score` slider isn't misread. Reconcile the OCR `0.85` default.
5. Every `continue` degradation records a **degradation event** surfaced in `chain_traces`
   (the trace infra already exists) → the UI shows "stage X degraded: all providers failed/below
   threshold" instead of silent loss.

---

## 7. Config shape & backward-compat

- `failure_policy` + `on_degraded` are new optional fields on `ChainGateConfig` with per-stage
  defaults applied at build time → **old stored configs load unchanged** (Pydantic defaults).
- No DB migration (pipeline is JSONB).
- Toggling `failure_policy` does NOT change embeddings → **not** an index-invalidating change
  (no reindex). Toggling gate thresholds that change which provider runs (and thus the output) — e.g.
  a different OCR/parse provider gets selected — *can* change output; treat `min_score`/duration/cost
  on parse/enrich/embed as reindex-relevant (decide Q5).

---

## 8. Discovery / UI exposure

- Gate fields (`min_score`, `max_duration_ms`, `max_cost_usd`) + `failure_policy` + `on_degraded`
  surface per stage in the discovery overlay (the ingestion stages already expose their gate).
- **Blocker (separate):** `pipeline.search.*` is NOT in discovery at all — so the rerank/q-transform
  chains+gates won't be UI-editable until the search-discovery gap is closed (tracked for the UI
  redesign). The ingestion gates/policies (S1/S2/S6) are exposable now.
- UI per stage: chain editor (ordered providers) + gate (score/time/cost) + a **failure-policy
  selector** (`raise` / `continue`) + (continue) `on_degraded`. This is the "rendre chaque étape
  paramétrable" the user asked for.

---

## 9. Observability

Reuse `chain_traces` / `embed_chain_traces` (already per-document): each records every attempt
(provider, score, duration, cost, succeeded, escalated, error) + the **final decision** (accepted
provider OR exhausted) + **degraded flag** + which gate tripped (score/time/cost). The UI surfaces
"why this provider, why it escalated, did the stage degrade" — turning today's invisible escalation
into a first-class signal.

---

## 10. Implementation phasing (step-by-step)

- **2a — Core + ingestion (the foundation):** add `failure_policy` (+`on_degraded`) to
  `ChainGateConfig`; make `Chain.call` honor it (`ChainExhaustedError` vs degraded outcome); wire
  `max_duration_ms`/`max_cost_usd` in the gate; migrate S1/S2/S6 call-sites off hardcoded
  raise/continue to the policy; per-stage defaults + validator (raise-only stages). Tests.
- **2b — Search & semantic:** rebuild rerank, query-transform, S4 semantic-embed on the
  `Chain` primitive (chain + gate + policy); unify the semantic embed config with `EmbedConfig`.
- **2c — Cleanup:** remove dead `ProviderChain`/`_PredicateGate`; unify empty-chain handling;
  reconcile OCR default + `enrich.max_budget_usd` vs gate cost cap; degradation events in traces.
- **2d — Discovery + UI:** expose gates+policy per stage; (depends on the search-discovery work for
  the search stages). Power-user stage panels.

Each sub-phase is independently shippable + reviewable.

---

## 11bis. RESOLVED DECISIONS (2026-06-25)

- **Q1 on_degraded default = `empty`** (best_effort stays available per-collection for experts).
- **Q2** parse/embed default = `raise`. ✅
- **Q3 NO raise-only restriction** — EVERY fallible stage accepts `raise` OR `continue` (expert
  choice). Defaults: parse/embed = raise, all others = continue. A `continue` parse/embed/chunk
  produces empty downstream (doc ends "done" with 0 chunks / indexed=false) — the expert's call.
- **Q4 BUDGET = DELETE EVERYTHING, no legacy.** Remove the entire budget/cost concept everywhere:
  `enrich.max_budget_usd`, gate `max_cost_usd`, ALL cost tracking (`cost_per_call`, `cost_usd`,
  `budget_spent` in chain attempts/traces, jobs, implicit_meta), AND Brique D `budget_cap_usd`
  (collection limit + 409-budget admission + `sum_budget_by_collection` + the DB column via
  migration) + MCP/frontend references. The gate therefore keeps only `min_score`,
  `max_duration_ms`, `failure_policy`, `on_degraded` (no `max_cost_usd`).
- **Q5** gate `min_score`/`max_duration_ms` on parse/enrich/embed → reindex-relevant; `failure_policy`
  and all search gates → NOT reindex-relevant. ✅
- **Q6** Do **ingestion first** (budget purge → 2a core+ingestion → 2c cleanup), DEFER 2b (search/
  semantic chains) and 2d (discovery+UI) to the UI redesign.

Implementation order: **CHUNK 1 budget purge** → **CHUNK 2 chain failure-policy (2a)** → **CHUNK 3
cleanup (2c)**. (2b/2d later with the UI redesign.)

## 11. Open decisions for the user (now resolved — see 11bis)

- **Q1 — `on_degraded` default**: `empty` (skip, safest) vs `best_effort` (use below-threshold
  result rather than nothing). Recommend `empty` default, `best_effort` opt-in.
- **Q2 — Defaults table (§4)**: agree S1/S6 = `raise`, everything else = `continue`?
- **Q3 — raise-only stages**: keep parse/chunk/embed as raise-only, or allow `continue` (e.g.
  "index nothing but keep the parsed doc")?
- **Q4 — Cost model**: fold `enrich.max_budget_usd` into the gate `max_cost_usd` (one cost concept),
  or keep a separate per-document enrich budget AND per-chain gate cost?
- **Q5 — Reindex semantics**: should changing a gate threshold on parse/enrich/embed flag
  `needs_reindex` (it can change which provider runs → different output)? Recommend yes for
  parse/enrich/embed gates, no for failure_policy and search gates.
- **Q6 — Scope/order**: do all of 2a→2d, or stop after 2a+2c (ingestion solid) and defer 2b/2d to
  the UI redesign?
