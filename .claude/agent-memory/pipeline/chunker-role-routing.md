---
name: chunker-role-routing
description: How chunk-role classification actually removes text from body chunks, and why a role tag alone can be inert scaffolding
metadata:
  type: project
---

# Chunker role → furniture routing (the "inert tag" trap)

`BaseChunkerNode.run` (chunk/base/node.py) splits projected passages by role: `role is BODY`
flows through the method's `_split` grouping; **every non-BODY role** (HEADER_FOOTER, TOC,
BOILERPLATE) is diverted to `__group_furniture` → one small disabled-by-role chunk per
`(role, page)`, kept but never embedded (`role_default_enabled` returns True only for BODY).

**Why this matters:** to make a class of repeated/furniture text stop leaking into body chunks,
it is SUFFICIENT to assign it a non-BODY `ChunkRole` in `PassageProjector.__role_for` — the
run-level split then routes it out automatically, the same path HEADER_FOOTER already used. There
is no separate "removal" step to write.

**The trap (real incident, 2026-07):** FIX 2/3 first shipped as scaffolding — a `normalize_text`
helper, config fields, and a `heading_only` field that were DEFINED but never READ/SET, and a
`__role_for` with no boilerplate branch. Every test stayed green because nothing exercised the new
paths; a live re-ingest proved all 11 chunks were still `role=body`. Lesson: for a chunker
classification change, the acceptance test must be BEHAVIORAL (assert the text is absent from body
chunks AND present as a disabled chunk), not just "the field exists". Green alone masked inert code.

## Where the two live-audit fixes landed
- Repeated boilerplate: `PassageProjector.__repeated_texts` (pre-pass keyed on distinct
  `provenance.page` counts, gated by `detect_repeated_boilerplate` / `boilerplate_min_pages` on
  `BaseChunkerConfig`) + a BOILERPLATE branch in `__role_for` AFTER header/footer and ToC.
- Heading-only orphans: `Passage.heading_only` set in `project()` for HEADING blocks;
  `BaseChunkerNode.__absorb_orphan_headings` folds a bare heading whose section owns no content
  FORWARD into the next passage (breadcrumb), or BACKWARD when it is the trailing passage. A
  heading that owns real content shares its section_key with that content → never orphan.

## VLM deflection guard (FIX 1, same audit)
Chat VLMs fall into assistant mode on an unlabelled chart (they address the user and ask for the
data, which then gets embedded). The fix is a node-level invariant, `_DESCRIPTION_GUARD`,
prepended to the system prompt inside `BaseVlmNode.run` — NOT a config default. This keeps the
per-class prompts in `ingest/stages/state.py` (hence the golden `default_blob.json`) byte-identical
while forcing a standalone visual description that never deflects, even if a user overrides the
per-collection prompt.
