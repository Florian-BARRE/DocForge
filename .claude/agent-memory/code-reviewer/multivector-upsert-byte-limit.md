---
name: multivector-upsert-byte-limit
description: ColBERT/multivector Qdrant upserts must be batched by ESTIMATED BYTES, not point count — a whole-document upsert of full-precision colbert floats crosses Qdrant's 32 MB max_request_size and 400s with a connection reset (surfaces as httpx.ReadError)
metadata:
  type: reference
---

A ColBERT multi-vector is dozens–hundreds of 1024-dim vectors PER POINT, and full-precision floats
serialize at ~22 bytes each. A whole-document upsert (even ~6 chunks) easily crosses Qdrant's default
**`max_request_size` = 32 MB**. Qdrant then rejects on the Content-Length **before reading the body**
→ an **instant 400** (~100µs) + connection reset. The qdrant-client sees `httpx.ReadError` /
`ResponseHandlingException` with an EMPTY message (the 400 body never arrives), which looks like a
timeout or a bad vector but is neither.

Signature that misleads:
- The worker error is `ResponseHandlingException:` (blank) wrapping `httpx.ReadError` — NOT a validation
  message. Easy to misread as a timeout (it is not — the 400 is instant) or an empty/invalid vector.
- It is INTERMITTENT by token count: a doc whose colbert total lands just under 32 MB succeeds; one just
  over fails. Same doc, same code → flaky. Do not chase "empty vector" — check the SERIALIZED BYTES.
- Per-point upsert of the SAME points all succeed (each < 32 MB); only the batch trips it. A quick
  isolation loop (upsert one struct at a time) that finds NO offending point is the tell: it's SIZE.
- Reproduce by building the batch with FULL-PRECISION floats (`random.uniform(...)`), not `0.01` — tiny
  reprs hide the size (a 0.02-float batch is ~4× smaller and passes, masking the bug).

**Fix (landed in `qdrant/apis/index_api.py` `QdrantIndexApi.upsert`):** batch by ESTIMATED PAYLOAD BYTES,
not point count. Point-count batching is blind to the wildly varying colbert token counts. Accumulate
points until ~16 MB (`__point_bytes` = float count × ~22 + overhead), flush, always ≥1 point/request.
Also raised the qdrant-client timeout from its 5 s default to 60 s (`qdrant/client.py`) — orthogonal but
right for heavy multivector indexing with `wait=true`.

**Review heuristic:** any code that upserts multivectors (colbert/late-interaction) or otherwise
variable-and-large vectors MUST bound the request by bytes. A `batch_size = N` constant over points is a
latent 32 MB bomb the moment vectors get big. See [[translator-drops-artefact-fields]] for the sibling
persistence-edge gotcha.
