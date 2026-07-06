---
name: enrich-trace-and-failure-traps
description: docforge-rework enrich stage — byte-carrying artefacts blow up the execution-record trace ~8x (foreach items_count mitigation is partial), enrich_apply mutates run_input in place, and one flaky figure fails the whole document.
metadata:
  type: project
---

Audit of the enrich-stage migration (clean-slate pipeline rewrite, `shared/libs/pipelines`). Three durable review heuristics for byte-carrying artefacts + per-item graphs.

**1. Byte-carrying artefacts explode the execution-record trace.**
`FlowEngine.__run_action` unconditionally sets `resolved_input=node_input.model_dump()` and `output=node_output.model_dump()` on EVERY node hop. When an Artifact carries raw bytes (`FigureItem.image`, IR crops), those bytes are re-serialized at every hop: extract in/out, each per-item clf in/out, ocr in/out, vlm in, apply in/out, plus group records. Measured ~8x blow-up (5×100 KB crops → ~3.8 MB record tree). The foreach's `items_count`-only output is a PARTIAL fix — it only stops the foreach-level re-dump, not the dominant per-node dumps. **Why:** the record tree is held in memory per run and will be persisted by the worker (not built yet). **How to apply:** whenever an artefact model gains a `bytes`/large field, flag the trace cost; the real fix is trimming what `model_dump` puts in the record (exclude byte fields), not the foreach.

**2. `enrich_apply` mutates `run_input["ir"]` in place — `output.ir IS run_input["ir"]`.** Pydantic (revalidate_instances=never) does not copy the nested model, so extract's and apply's `Consumes.ir` are the same object as the run input; apply fills figure slots in place (documented as intentional, to avoid re-copying crops). **How to apply:** safe only because apply runs ONCE outside the ForEach; but any dry-run/preview that reuses the run input after execute() sees a mutated IR. Watch for aliasing whenever a node returns the same artefact it consumed from run input.

**3. Enrichment is all-or-nothing per document.** Every enrich/ocr/vlm node defaults to `ERROR_POLICY.FAIL` and the ForEach fails loudly on ANY item failure ("échec d'item = échec bruyant"). CONFIRMED: one figure's transient classifier 503 → whole ForEach FAILED → whole document ingestion returns output None; the healthy figures' enrichment is discarded. **How to apply:** for a best-effort enhancement stage this fragility is a design decision — either the providers need `ERROR_POLICY.SKIP` or the default topology needs OnFailure degradation edges. Surface it on any per-item enhancement graph.

Related: [[foreach-primitive-traps]], [[pipeline-engine-edge-selection]]. Note: FromFirst binding (convergence join after ScoreBelow/OnFailure fork) validates correctly (downstream/unknown/type-mismatch candidates all flagged) and resolves first-present-candidate in priority order — no defect found there.
