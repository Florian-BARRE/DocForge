---
name: translator-drops-artefact-fields
description: Pipeline tags a new Chunk/IR artefact field but the worker IR→DB translator omits it, so the DB row silently falls back to server_default — feature half-wired
metadata:
  type: feedback
---

When a pipeline node starts populating a NEW field on a public_models artefact (e.g. `Chunk.role`
added in the enable/disable feature), the artefact is only half the story. The field must also be
propagated to the DB at the IR→DB boundary: `worker/backend/libs/persistence/translator.py`
(`RunTranslator._translate_chunks`, the `Chunk(...)` ORM row construction ~line 164). The translator
builds ORM rows field-by-field explicitly — an omitted field is NOT copied from the artefact; it
falls back to the column's `server_default` (e.g. `role` server_default `"body"`).

**Why:** During enable/disable P3, the chunker correctly set `chunk.role = HEADER_FOOTER` and the
embedder correctly skipped it (no Qdrant point), but the translator never wrote `role=chunk.role`.
Net effect: disabled-by-role chunks persist as `role="body"` → `role_default_enabled("body")` is True
→ effective-enabled resolves True. The chunk is not lost, but it is mis-classified as enabled body —
defeating both "don't lose the classification" and any role-keyed re-embed. See [[chunk-roles-disabled]].

**How to apply:** Whenever a diff adds a field to an artefact under `public_models/` that has a
matching DB column, grep `translator.py` for that field being set on the ORM row. If it is not set,
flag it — the artefact tag never reaches the DB. Also check the worker test actually asserts the
persisted ROW carries the value (`row.role == ...`), not just that a row/point exists: a test that
only counts rows and points gives false confidence and hides exactly this gap. Note ORM rows are
unflushed in the translator output, so `server_default` is not visible in-memory (the field reads
`None`) — asserting it needs a DB round-trip or an explicit constructor arg.
