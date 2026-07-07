---
name: r2-stage-restructure-pattern
description: How to restructure a legacy sN_* ingest stage into native steps (the R2 chantier) — decomposition, result relocation, importer repointing, deletion, and the parity gotchas.
metadata:
  type: project
---

The R2 chantier rewrites each ingest stage into REAL native steps under
`common_libs/pipeline/ingest/stages/<name>/` and DELETES the legacy `stages/sN_*` package.
Exemplars committed: `ingest/` (3 steps) and `parsing/` (3 steps: parse → figure_render → markdown).

**Why:** dynamic self-describing stage architecture — stages own real steps, not delegate to a
legacy inner. **How to apply:** follow this template for enrich/chunk/contextualize/metagen/embed_index.

## Native package layout (per stage)
- `core.py` — the `@register_stage` stage (subclasses `IngestStage`) + a frozen `<Name>Resources`
  dependency bundle. The assembler always calls `stage_cls(inner)` with ONE arg, so bundle deps.
- `steps/<verb>_step.py` — one `IngestStep` per real operation; declare `KEY/NAME/DESCRIPTION/
  CONSUMES/PRODUCES` ClassVars; real per-step error handling + logging.
- `scratch.py` — a mutable `<Name>Scratch` dataclass + `<NAME>_SCRATCH_KEY` for inter-step hand-off
  via `ctx.aux[KEY]` (durable ctx fields are only the stage's declared PRODUCES).
- `result.py` — the relocated former `SNResult` (clean name, e.g. `ParseResult`), IDENTICAL fields.
- `helpers.py` — static `<Name>Helpers` for pure transforms (no I/O).
- `__init__.py` (stage + steps) — labeled sections + `__all__`.

## Chain-backed step (e.g. ParseStep)
A step that drives a provider chain subclasses `IngestStep` (NOT the generic `base.step.ChainStep`),
holds the `Chain`, runs ONE `chain.call(lambda p: p.<verb>(...))`, and overrides `fingerprint_params`
(`{"<chain>": chain.signature()}`), `trace_attempts`/`trace_final_provider` (from the last outcome),
and `describe()` to emit `kind="chain"` + `category` + `providers`. This is the `EmbedStep` precedent.

## Parity invariants (MUST preserve byte-for-byte)
- Stage SPEC: same `key=StageKey.X`, `code_version`, `cache_policy`, `error_policy`, AFTER, and
  stage-level CONSUMES/PRODUCES as the legacy adapter.
- **Override `fingerprint_params()` on the stage** to return the legacy node-key dict (e.g.
  `{"parse_chain": sig}`), NOT the inherited per-step aggregate `{step.key: …}` — the aggregate
  changes the Merkle node-cache key and breaks cache parity.
- The result dataclass fields are identical, because the worker node-cache codec
  (`cache_codec`/`cache_encoder`) serializes by FIELD ACCESS, not type name — so renaming the type
  is byte-safe as long as fields match.
- Markdown S3 key is keyed by the PARSE node fingerprint: read `ctx.fingerprints["parse"]` (the stage
  key), never the step KEY. Fallback string kept as `"s1_no_fingerprint"` for key parity (only used
  when no fingerprint, i.e. tests/dry — production always sets it).

## Importer repointing
Repoint every `SNResult` importer to the new `ingest.stages.<name>.result` path. For parse these were:
`context.py` (TYPE_CHECKING + field), `stages/__init__.py` (remove entries), and the worker
orchestrator `cache_codec / cache_encoder / cache_io / result / s012_persist / trace_flush`. Also fix
stale docstring/comment mentions of the old type name so the grep proof is truly zero.

## Assembler wiring
`stage_assembler._build_inner` returns the resources bundle for the key (e.g.
`ParseResources(parse_chain=registry._build_parser_chain(...), s3=deps.s3)`); the chain is still built
lazily via the shared `registry._build_*` builders — steps never import provider bricks directly.

## Gotchas
- Importing the relocated `result` submodule triggers `ingest/stages/__init__.py` (eager stage
  registration). That's fine at worker runtime; keep `result.py` light (DocumentIR under TYPE_CHECKING)
  so it pulls in no heavy deps.
- Tests that run a step end-to-end must STUB PyMuPDF rendering (`_render_figure_crops_sync`) — the sync
  renderer does NOT wrap `fitz.open()` in try/except, so fake bytes raise and fail the stage.
- After test runs, re-`Read` a file before `Edit` (harness state-tracking re-requires it).
- Parity tests assert `by_key["<key>"]._resources.<chain>.signature()` (native stage) — the old
  delegation tests asserted `._inner` against the legacy stage type; update both
  `test_build_pipeline_parity.py` and `test_registry_schema.py`.
- Run: `cd src/docforge && unset VIRTUAL_ENV && uv run --project common pytest tests/units -q`.
