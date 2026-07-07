---
name: ingestion-config-audit
description: Per-option wiring map of the S0-S6 ingestion config — dead config, discovery gaps, two config surfaces
metadata:
  type: project
---

# Ingestion config (S0-S6) — wiring map & gaps

Audit (2026-06-25) of every editable ingestion option, for the UI redesign. Verify file:line before acting — code drifts.

## Two config surfaces (don't conflate)
- **S0 conditions** = `collection` table COLUMNS (`storage/postgres/models/collection.py`) + `metadata_field` table. Edited via config router; echoed by `GET /collections/{id}/config/state`. **NOT in `/discovery` dynamic_fields.**
- **S1-S6 pipeline** = `collection.pipeline` jsonb → `PipelineConfig` (`config/pipeline/pipeline.py`). Discovery overlays every `pipeline.*` knob via `discovery/overlays.py` + `pipeline/assembly/stage_descriptors.py`.

Real ingestion always loads the full per-collection `PipelineConfig` (`worker/.../worker/tasks.py`) → `StageResolver.resolve` → `registry.build_stages` → `ChunkStageAssembler` (full S4). The lossy `registry.build_enrich_and_chunk_stages` (drops S4 atomic/heading/hierarchical) is ONLY the startup default stack (no collection) — not the ingestion path.

## DEAD config (editable but consumed nowhere)
- ~~**`enrich.chart_to_data`**~~ — FIXED 2026-06-25. Threaded EnrichConfig.chart_to_data → registry `_build_s2` → `S2EnrichStage` → `FigureEnricher` → `FigureRoutingHelpers.maybe_vlm`, where `use_chart_schema = (kind==CHART) and chart_to_data` (`s2_enrich/figure_routing.py:96`). False (default) → CHART gets VLM description only, no data_table; also folded into S2 fingerprint (`core.py params_for_fingerprint`). NB: this DOES change the old always-on behavior — that was the bug.
- **`collection.allowed_providers`** column — no enforcement found.
- **gate `max_duration_ms` / `max_cost_usd`** (all stages) — parsed but not enforced (`providers/chain_gate.py` Phase A), and not in discovery.

## Wired but NOT in discovery (invisible to a discovery-driven UI)
- **`chunk.atomic.{tables,figures,formulas,keep_caption_with_figure}`** — honored (HeadingWalker via `chunk_stage_assembler.py`), no overlay.
- **`chunk.heading_rules`** (list of {level,pattern}) — honored (`s4_chunk/core.py` compiles them), no overlay.
- **`embed.sparse`** (separate sparse backend) — honored (`s6_builder.py` threads it), no overlay. Only way to get hybrid with a dense-only chain.

## Partial / misdesigned
- All gate `min_score` are wired but INERT on default 1-provider chains (escalation needs 2+ providers).
- `unknown_field_policy` / `locality_policy`: only the strict value (`reject` / `on_premise_only`) does anything; other strings silently disable the check (should be real enums).
- `locality_checks.py` has a stray dead block after the embed loop (re-checks last `embed_url`, wrong field path `embed.provider`).
- `embedding_model` column duplicates `pipeline.embed.chain[0].model` (two sources of truth).
- ~~`vit_onnx` classifier reports `selectable=true` always~~ — FIXED 2026-06-25. `VitOnnxConfig.availability(cfg, model_path=None)` now returns `(False, "requires a model_path to an .onnx file (set per-collection)")` with no usable path; new `VitOnnxConfig.selectable()` classmethod mirrors it. The shared describe loop (`assembly/describe.py`) reads an optional `selectable` hook via getattr (defaults True for all other providers). Discovery now shows vit_onnx available=false/selectable=false + the note.

## Cleanest stage
S5 contextualize — all 4 knobs wired AND in discovery.
