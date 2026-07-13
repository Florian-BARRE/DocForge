---
name: pipeline-memory
description: Pipeline architecture for the docforge-rework pure graph engine — node contract, families, graph mechanics, validation, and live topic pointers
metadata:
  type: project
---

# Pipeline — Memory Index

The ingestion engine of the ACTIVE product `src/docforge-rework/`: a **pure graph engine** at
`shared/libs/pipelines/` (base/engine/edit/validation/nodes/ingest). Reference doc:
`src/docforge-rework/PIPELINE.md`; cheat-sheet: `.claude/rules/architecture.md`.

## Node contract

A node is **pure**: `Config` (a `NodeConfig`, `extra="forbid"`) + Consume→Produce, **zero DB/S3 I/O**.
It declares via `describe()`: typed IN/OUT slots (each `Artifact`/`list[Artifact]` **must** carry a
description or a test rejects it), `family`/`kind`, `UNIQUE_IN_GRAPH`, `scored`, `switch_fields`,
`error_policy`. Persistence happens at the edges IN THE WORKER via the `Database` façade — never inside
a node.

## Families & placement

- Stage-dedicated: `intake · converter · parser · render · enrich · chunker · contextualize · metagen`.
  Generic reusable: `embed · ocr · vlm · llm` (+ the `openai_compat` factory).
- Kind convention: no family+kind redundancy — `(ocr, mistral)` not `mistral_ocr`. A new provider = one
  more kind in its family, interchangeable in the UI, zero engine change.
- Where to put it: generic provider → `shared/libs/pipelines/nodes/<family>/`; ingest-stage node →
  `shared/libs/pipelines/ingest/nodes/<stage>/`; any DB/S3/Qdrant access → a **façade** under
  `shared/libs/services/db/facades/`, called by the worker.

## Graph mechanics (`shared_libs.pipelines.base`)

- Transitions (control): `OnSuccess · OnFailure · ScoreBelow(t) · WhenEquals(field,val) · Always`.
  Selection priority: `ScoreBelow > WhenEquals > OnSuccess/OnFailure > Always`.
- Bindings (data): `FromRunInput · FromNode(node_id, field) · FromGroupInput · FromFirst([…])`.
- `ForEach`: sub-graph per item; body terminals produce the SAME single-slot Artifact → `items: list`
  (order preserved, one execution record per item, an item failure fails loudly).
- `UNIQUE_IN_GRAPH=True` → a 2nd instance of the kind is a wiring error (`duplicate_unique_node`).
- Validation (`GraphValidator`, before any spend): single entry · no cycle · no ambiguous fan-out ·
  upstream bindings present + type-compatible · `ScoreBelow` ⇒ producer is `scored` · single-use
  uniqueness. A broken blob returns as DATA (`valid=false` + issues), never an HTTP error.

## Topic files

- [Device not in config](device-not-in-config.md) — GPU/device is a deployment env decision, never a per-collection provider config field.
- [Flow-engine stage ports](flow-engine-stage-ports.md) — the generic graph engine (`shared/libs/pipelines/`): node/transition model, inter-stage binding spine, and how v1 stages were ported.
- [Provider raise-on-failure](provider_raise_on_failure.md) — providers must RAISE on engine failure (not return a degraded result) so the escalation chain advances.
- [Search result-count semantics](search-result-count-semantics.md) — request `top_k` is authoritative; `candidate_k` is the pre-rerank pool; `top_n`/`grouping.group_by` removed.
- [Stage layer](stage-layer.md) — the product-level stage view over the ingest graph: where it lives, its invariants, the state-based compiler design.
- [Chain / escalation mechanism](chain-mechanism.md) — fallback-chain topology in build/chain.py; enrich + PARSE (P3) + EMBED (P4) chain-capable; parse_chain/embed_chain replaced kind/config fields; embed non-scored + UNIQUE-capped + dynamic face; segment.output anchors. P5/P6 pending.
- [Metagen externalization (P5)](metagen-externalization.md) — metagen LLM call split into generic `structgen` + metagen prep/apply/skip nodes wired by ForEach; on_error is a graph edge; the ForEach exits/item_type fact that makes a fail-soft terminal validate; FlowEngine returns FAILED (never raises).
- [Selectable flag + contextualize externalization (P6)](selectable-flag.md) — `SELECTABLE` describe flag hides internal wiring kinds from the palette (filter in `NodeRegistry.catalog`); contextualize LLM split into `prep → ForEach(generic-llm chain [+ keep_raw]) → llm_apply`, positional zip join; P6a byte-safe temp kind `llm_prep` (monolith stays), P6b renames to `llm`.
- [Externalization drift audit (post-P6)](externalization-drift-audit.md) — verdict: pure-engine/uniform-node/ONE-assembler principle INTACT; ChainFragmentBuilder+ChainWalker+ChainRules genuinely shared 5×; the one real copy-paste drift = metagen_body ≈ contextualize_body (collapse to one ForEachChainBodyBuilder); Segment vs StackPosition nest (not competing).
- [Chunker role routing + inert-tag trap](chunker-role-routing.md) — non-BODY role auto-diverts a passage out of body chunks (assigning the role is the whole fix); the 2026-07 live-audit fixes: repeated-boilerplate role, heading-only orphan fold, VLM anti-deflection guard baked into BaseVlmNode (golden stays byte-identical).
- [Tables already serialized + late-chunking offsets](table-and-late-chunking.md) — tables ARE markdown-rendered at chunk projection (don't add an enrich/table node); late-chunking token spans must be computed server-side (BGE-M3 tokenizer != chunker tiktoken).
