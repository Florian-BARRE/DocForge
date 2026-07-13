---
name: pipeline-blob-validation
description: PipelineBlobValidator is the single chokepoint that build+validates a collection's pipeline blob; called on collection create/update AND before every document enqueue (fail-fast, no wasted job)
metadata:
  type: reference
---

`app/backend/utils/pipeline_validation.py` — `PipelineBlobValidator.validate(blob)` (static-only):
1. builds the blob via `CONTEXT.pipeline_builder.build` — an unknown/removed node kind raises
   `BuildError`, caught and turned into a **422** naming the offending node;
2. runs `CONTEXT.graph_validator.validate(group)` — structural issues become the 422 payload.

It is the ONE chokepoint (extracted from the old inline `_validate_pipeline`), called from:
- `routers/collections/router.py` create + update (validate on every write), and
- `routers/documents/router.py` `upload_document` — right after the collection-exists check and
  BEFORE any read/dedup/store/admit/enqueue, so a collection whose STORED blob went stale (a kind
  removed by an engine change, e.g. P5 dropping `(metagen,chunk)`) 422s with the node name and
  spends nothing, instead of a job that dies at run.

Why it matters: stored collection blobs are NOT auto-migrated when the registry changes; this
validator is the fail-fast guard. See project memory [[stored-blob-staleness]] for the full gap
(fail-fast + manual PATCH repair only; no migration framework yet).
