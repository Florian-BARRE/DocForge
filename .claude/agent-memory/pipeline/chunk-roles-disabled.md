---
name: chunk-roles-disabled
description: P3 reversible enable/disable — chunker keeps header/footer+toc as role-tagged disabled chunks; embed skips disabled-by-role chunks (no vector), they still persist
metadata:
  type: project
---

# Chunk roles + disabled-by-role embed skip (P3 of the enable/disable feature)

Phase 3 of the 6-phase reversible enable/disable feature (pipeline side only — no DB/API/search).
Policy lives ONCE in `shared/libs/public_models/chunk_role.py`: `ChunkRole` (body/header_footer/
toc/boilerplate) + `role_default_enabled(role)` (BODY only → True). Import it, never re-encode.

**Why:** don't lose ingestion. Furniture (header/footer) and ToC are KEPT as chunks (reversible,
inspectable, re-enablable) but disabled-by-default → not embedded (owner accepted "non-embedded →
no Qdrant cost"), yet still flow to the delivery bundle + persistence with raw text + role.

## Chunker (ingest/nodes/chunk/base)

- `Passage` carries `role` (`passages.py`). `PassageProjector` no longer drops `HEADER_FOOTER` —
  it renders its native text and labels it via `__role_for(block, heading_path)`:
  HEADER_FOOTER block-type → HEADER_FOOTER; ToC inferred from ancestry (any heading whose FULL
  normalized text ∈ `_TOC_TITLES` allow-list — EXACT match, never substring, so "Table of
  contributions" stays BODY). BOILERPLATE is reserved (no reliable IR signal yet).
- `BaseChunkerNode.run` partitions: only BODY passages go through `_split` (the method's grouping);
  furniture is grouped by (role, page) in `__group_furniture` and APPENDED AFTER body. Rationale:
  running header/footer has no single reading position; appending keeps body chunk ordinals/
  positions contiguous → contextualize window/neighbour logic over body unchanged. `__finalize`
  sets `chunk.role = group[0].role` (groups are role-homogeneous by construction).

## Embed (nodes/embed/base/node.py — GENERIC node, but chunk-scoped already)

- `run` filters to `enabled = [c for c in chunks if role_default_enabled(c.role)]` and embeds ONLY
  those. Disabled chunks get NO ChunkVectors entry. Topology-STABLE (signature unchanged) → the
  golden `default_blob.json` stays byte-identical (verified: fixture absent from git diff). All-BODY
  input = byte-identical behaviour (existing embed tests unchanged).

## Persistence (untouched — proven, not modified)

`worker/persistence/translator.py` links vectors to chunks by `chunk_id`; a chunk without a vector
item just gets no Qdrant point (the "no embed stage → no points" path). So disabled chunks persist
as chunk rows with no point, for free. NOTE: the translator does NOT yet write the `role` column
(P2 added it) — wiring role into the chunk row is a later phase, out of P3 scope.

## Deferred (flagged follow-up)

contextualize/llm + metagen LLM-skip for disabled chunks was NOT done: those stages use a
ForEach + positional-zip join (apply zips completions back by index), so filtering disabled chunks
would desync the join. Embed-skip (the must) is clean; the LLM-skip is the riskier bit → left as a
follow-up. Furniture text does leak into the contextualize FULL document view (built from all
chunks) — minor noise, same follow-up.
