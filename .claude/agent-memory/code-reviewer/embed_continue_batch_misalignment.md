---
name: embed-continue-batch-misalignment
description: S6 embed failure_policy=continue skips a batch with `continue`, misaligning content_dense vs index_chunks → wrong/missing Qdrant vectors + IndexError in embed_values
metadata:
  type: project
---

# S6 embed `continue` skipped-batch misalignment (chain failure-policy work, 2026-06-25)

`S6Embedder.embed_texts` batches texts and, under `failure_policy="continue"`, on a degraded
batch does `continue` (skips it) instead of emitting placeholder vectors. This breaks the
**positional contract** that `all_dense[i]` corresponds to `index_chunks[i]`.

**Why:** the result lists feed `QdrantUpsertHelpers._build_point` which aligns purely by index
(`v = vecs[index] if index < len(vecs) else None`). A shorter/shifted `content_dense`:
- gives chunks AFTER the skipped batch the WRONG neighbour's vector (silent corruption),
- gives chunks beyond `len(content_dense)` `None` → indexed with no content vector (silently
  unsearchable), and
- in `embed_values`, `dense_out[i] = dense[j]` raises `IndexError` when `dense` is short — turning
  a "continue" into an uncaught crash (worker marks doc failed), defeating the whole point of
  `continue`.

**How to apply:** any chain-`call` whose result is consumed POSITIONALLY (zipped/indexed against
an input list) must, on a degraded/None outcome, emit a same-length placeholder (e.g. per-text
`None` dense vectors) — NOT drop the batch. Single-text/single-batch tests hide this; demand a
multi-batch (≥2 batches, middle batch fails) test before approving any "skip the batch" degraded
path. Default embed gate is `raise` so this only bites collections that opt into `continue`, but
it IS a Qdrant-corruption path. Related: [[search_pipeline_antipatterns]].
