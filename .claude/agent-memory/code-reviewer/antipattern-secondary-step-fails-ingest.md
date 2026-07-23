# Anti-pattern: a best-effort secondary step inside the fatal ingest try

`worker/backend/libs/jobs/core.py :: ingest_document` persists in a hard order (S3 → PG one-tx
`save()` → Qdrant `index()`). Anything added AFTER `index()` but still inside the outer `try` whose
`except` calls `mark_failed` + re-raises (arq retry) is dangerous: by then the expensive work is
durably committed, so if the late step throws (a transient Qdrant `set_payload`/patch hiccup) a
**fully-ingested, searchable document gets marked FAILED** and arq re-runs the WHOLE pipeline —
re-embed, re-translate, `delete_for_document` + re-insert chunks with NEW uuids (old Qdrant points
orphan). If retries exhaust, a complete document is stuck FAILED forever.

Rule: post-`index()` denormalization / secondary-store steps (e.g. filterable-metadata
`sync_document_filter_payloads`) are **best-effort** — wrap in their own `try/except`, log a warning,
fall through to `mark_done`. There must be an explicit repair path (a backfill job) so the secondary
data is eventually consistent without failing a good ingestion. Caught in the filterable-meta
denormalization review (fixed: step 5 got its own try/except). Sibling lesson to
[[reindex_staleness_coherence]] and [[async_teardown_swallow]].
