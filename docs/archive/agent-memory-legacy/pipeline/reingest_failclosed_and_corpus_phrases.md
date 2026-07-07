---
name: reingest-failclosed-and-corpus-phrases
description: Two recurring false-alarm classes — the S0 original-download fail-closed gap on reingest, and corpus searchable_phrases shared across formats
metadata:
  type: project
---

Two diagnoses from the 2026-06-25 live-suite triage. Both surfaced as "bugs" but the product was
mostly correct; the real fix was small (fail-closed) + a test-expectation fix.

## 1. Reingest "original not found" — fail-closed gap (real, minimal fix)

`StageEngine.run` (worker/libs/pipeline/orchestrator/core.py) downloads the original in **step 2**,
which is OUTSIDE all the fail-closed guards (`guarded_run` for S0/S1/S2, `run_s456` for S4/S5/S6,
the persist_s012 try/except). So if the original blob is genuinely missing, the download raised and
the document was left in its pre-run status — on a force reingest that is `pending`, which the API
maps to "running" forever. That violates the [[document-status-state-machine]] guarantee (a doc must
reach a TERMINAL state). Fix: wrap the step-2 download; on failure `S012PersistHelpers.mark_failed`
then re-raise (so arq still retries and the final state is `failed`, never stuck `pending`).
Regression test: `test_engine_marks_document_failed_when_original_missing` in
`tests/units/test_pipeline_fail_closed.py` (fake S3 whose `download` raises KeyError;
`pipeline_config=None` so `StageResolver.resolve` returns defaults and never touches the None stages).

**The blob lifecycle itself is NOT buggy:** collection delete keeps a shared content-addressed
original (`is_source_hash_shared` → `blobs_kept_shared=N`), and a clean force-reingest reaches `done`.
The classic false alarm is a repro that (a) polls with `wait_done` — which returns the instant
`chunk_count>0`, and a force reingest NEVER clears the previous chunks, so it returns immediately on a
stale `pending` snapshot before the worker even starts — and/or (b) deletes the 2nd collection right
after the reingest POST, racing the async worker and removing the (now-unshared) original + doc row
out from under the in-flight job. To verify reingest, poll the REAL `status` to `done|error|failed`
and never delete the collection until after a terminal status.

## 2. Corpus searchable_phrase is shared across formats (test-expectation, not product)

`tests/corpus/catalog.py::_PHRASE` is keyed by `(doc_type, language)` ONLY — so every format of a
given pair carries the IDENTICAL phrase: `report_fr` docx/html/pptx + `data_fr` xlsx + baked
legacy_xls/legacy_ppt all share one phrase (6 docs); `contract_fr` docx + legacy_doc + native_pdf
share another (3 docs). Search returns CHUNK-level hits, so a doc's own chunks compete with several
siblings carrying the same phrase. On the full `ingested_corpus`, `top_k=10` is fully consumed by
sibling chunks before the target's first chunk appears (target reliably appears by ~rank 10, i.e.
needs `top_k>=~20`). The doc IS correctly indexed (dense+sparse). Fix was to raise `top_k` to 30 in
`test_finds_target_document` with a comment — NOT a relevance/indexing bug. When asserting "a query
finds a specific doc" on this corpus, either use `top_k>=30` or scope to one document/format.
