---
name: flow-engine-stage-ports
description: The NEW generic flow engine (common_libs/pipelines plural) — node/transition model, inter-stage binding spine, and how stages are ported from v1
metadata:
  type: project
---

# Flow engine — stage port pattern (`common_libs/pipelines/` plural)

A SECOND, from-scratch pipeline engine — distinct from the `common_libs/pipeline/` (singular)
strangler in [[dynamic-stage-architecture]]. Branch `rewrite/pipelines-node-engine`. Engine in
`common_libs/pipelines/flow/`; v1 source kept at `common_libs/pipelines/core/ingest/stages/<stage>/`.

## The model (import from `common_libs.pipelines.flow`)

- A node is an **ActionNode** (leaf: `async execute(ctx) -> NodeOutput`; `ctx.input` = resolved typed
  Input, `ctx.service("name")` = injected service) or a **GroupNode** (children wired by Transitions).
- A **stage = a GroupNode**. Control shape EMERGES from edge conditions, not a subclass:
  `Condition.ALWAYS` = sequence, `SCORE_BELOW` = escalation (reads output `.score`), `ON_FAILURE` = fallback.
- **Data axis** = typed Input fields bound via Annotated markers: `FromNode("<sibling id>","field")`,
  `FromGroupInput("field")` (the enclosing group's input), `FromRunInput(field, required=)` (run input).
- `assemble(outputs, terminal)` builds the group Output; **default = terminal** (the natural single-node
  / escalation shape). A multi-node SEQUENCE overrides assemble to combine children (see ingest).
- `FlowEngine().run(root, RunContext(run_input, ServiceRegistry(items={...})))` -> `(output, NodeReport)`.
  Report status enum: `ReportStatus.OK` (== "ok").

## Inter-stage binding spine (bind stage Inputs EXACTLY so stages compose)

- ingest.Output: {source_hash, original_format, original_key, pdf_key, converted, page_count, needs_ocr, media_type}
- parse.Output: ParserOutput {ir, score}
- enrich: in {ir<-FromNode("parse","ir")}; out {ir}
- chunk: in {ir<-FromNode("enrich","ir")}; out {chunks, chunk_result}
- contextualize: in {chunks<-FromNode("chunk","chunks"), ir<-FromNode("enrich","ir")}; out {chunks}
- metagen: in {chunks<-FromNode("contextualize","chunks"), ir<-FromNode("enrich","ir"), doc_user_meta<-FromRunInput(required=False)}; out {chunks, doc_meta}
- embed_index: in {chunks<-FromNode("metagen","chunks"), collection_id<-FromRunInput(required=False), metadata_fields<-FromRunInput(required=False)}; out {embed_result}

## Port pattern (verbatim domain reuse, restructured into nodes)

- ONE FILE PER NODE under `<stage>/nodes/<node>.py`; the stage in `<stage>/stage.py`; `__init__` exports.
- REUSE the v1 algorithm verbatim (import the chunker / contextualizer / embed-index helpers); you are
  RESTRUCTURING into flow nodes, not rewriting. Domain logic stays at the v1 `core/.../chunker/` path.
- Node Input binds with `FromGroupInput()`; the STAGE Input binds with `FromNode("<prev stage>", …)`.
- Provider/infra come via `ctx.service(name)` (object_store/qdrant/postgres/serializer + provider
  instances). Domain ENGINES built from config (chunker, contextualizer) are constructor-injected into
  the node by the builder — NOT a service. NO hardcoded URLs/hosts in nodes.

## Done

- **ingest** (sequence: content_address->convert->probe, assemble from all three).
- **parse** (escalation: ParseStage over ParserNode candidates wired by SCORE_BELOW; base downloads PDF
  + delegates to `_parse`; degrades to empty IR score 0 with no pdf_key).
- **chunk** (DONE, validated): `chunk/` = single-node group. `ChunkNode` (`nodes/chunk.py`) wraps the v1
  `StructureAwareChunker` (from `core/ingest/stages/chunk/steps/chunk/chunker`); Input `ir<-FromGroupInput`,
  Output {chunks: list[Chunk], chunk_result: S4Result}. `ChunkStage` Input `ir<-FromNode("enrich","ir")`,
  Output = ChunkNodeOutput (default assemble). Engine constructor-injected (default = TokenBudgetSplitter);
  the builder fills the splitter from config later. A one-node group = `super().__init__("chunk",[node],[])`.

## Gotchas

- A Pydantic model in Annotated metadata is mis-read as the field type — the binding MARKERS are frozen
  dataclasses (FromNode/FromGroupInput/FromRunInput), already handled by the flow package.
- Validate any stage with a scratchpad script: stub the upstream sibling node (e.g. a `StubEnrich`
  producing `ir`), wire `[stub -> stage]` in a `GroupNode("pipeline", …)`, run on `FlowEngine`, assert
  `report.status == ReportStatus.OK` + the typed Output shape. Run from `src/docforge/common` with
  `unset VIRTUAL_ENV && uv run --project common python <script>`.
