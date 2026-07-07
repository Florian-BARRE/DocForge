---
name: flow-engine-stage-port
description: How to port a v1 stage to the new generic flow engine (common_libs/pipelines/flow) on branch rewrite/pipelines-node-engine
metadata:
  type: project
---

# Porting a v1 stage to the flow engine

Branch `rewrite/pipelines-node-engine`. The new generic engine lives at
`common_libs/pipelines/flow/` (FlowEngine + ActionNode/GroupNode + typed IO bindings + Transitions).
Ported stages live at `common_libs/pipelines/<stage>/` (stage.py + one file per node under nodes/).

**Why:** the strangler rewrite replaces the v1 `Pipeline→Stage→Step→Brick` tree
(`common_libs/pipelines/core/…`) with a self-describing 2-node-kind tree. Exemplars to imitate:
`pipelines/ingest/` (sequence) and `pipelines/parse/` (escalation).

**How to apply — the mechanical translation from a v1 stage:**
- v1 `FromParent()` (read the enclosing stage input) → flow `FromGroupInput()`.
- v1 `FromSibling(producer="X", field="Y")` → flow `FromNode("X", "Y")`.
- v1 `FromRunInput(required=False)` → flow `FromRunInput(required=False)` (unchanged).
- A v1 Step (`LeafNode` + SPEC + Context + REQUIRES/ChainRef/ServiceRef) → a flow `ActionNode` with
  `Input`/`Output` ClassVars and `execute(ctx)`. Services come via `ctx.service("name")` (NO REQUIRES
  declaration, NO per-step Context subclass) — the registry is injected at run via `ServiceRegistry`.
- A v1 Stage → a flow `GroupNode`; wire children with `Transition(...)` ALWAYS edges (sequence) or
  `Condition.SCORE_BELOW` edges (escalation). Override `assemble(outputs, terminal)` to build the typed
  stage Output (default = terminal node's output).
- Domain helpers (embed/index/chunker/contextualizer) are ALGORITHM code — copy verbatim, only rename
  the class; they import `common_libs.pipelines.capabilities.chain` + `common_libs.search.field_index`
  + `common_libs.domain.*`, all unchanged.

**Inter-stage spine** (bind stage Inputs to these exact producers so stages compose): ingest→parse→
enrich→chunk→contextualize→metagen→embed_index. embed_index Input: `chunks <- FromNode("metagen",
"chunks")`, `doc_meta <- FromNode("metagen","doc_meta")` (needed for filterable payloads), `collection_id`
+ `metadata_fields <- FromRunInput(required=False)`. collection_id may be None — the worker's
EngineHooks.should_run gates the whole stage; nodes keep the empty-chunks no-op guards.

**Validate offline:** wrap the stage in a tiny GroupNode with a fake producer node (id = the producer
the stage binds to) + fake services, run on `FlowEngine()` with a `RunContext`, assert
`report.status == "ok"` and the typed Output. Patch real repo I/O (e.g. `ChunkRepository.bulk_insert`)
to an async no-op for a pure flow test. Run from `src/docforge/common` with
`PYTHONPATH=…/src/docforge/common unset VIRTUAL_ENV && uv run --project common python <script>`.

See [[dynamic-stage-architecture]] for the broader refactor context.
