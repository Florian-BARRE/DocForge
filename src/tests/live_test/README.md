# Live end-to-end tests

Real tests against the **running** stack — Gotenberg → Docling → TEI → Qdrant → Postgres — via the
real HTTP API, on the committed corpus. **Auto-skipped** when the stack is unreachable (so a normal
`units` run stays green without Docker). Everything is **local** (TEI embed + TEI reranker, no
external APIs); S2 enrichment stays off — the suite asserts structural extraction.

## Run

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
cd src/docforge && uv run pytest tests/live_test -v -s        # -s shows [calib] structure lines
```
Override endpoints with `DOCFORGE_TEST_API_URL` / `DOCFORGE_TEST_QDRANT_URL` /
`DOCFORGE_TEST_RERANKER_URL`.

## Fixtures (`conftest.py`)

- `live_client` — `LiveClient`; **skips the whole tier** if the API is down.
- `corpus` — loads the committed corpus once per session.
- `ingested_corpus` — ingests the **whole** corpus once and shares it (read-only tests reuse it).
- `make_collection` — disposable, auto-cleaned collections for mutating tests.

## Files (what each exercises)

ingestion+structure / hybrid search / config CRUD+rollback / metadata ±reindex / staleness /
reingest / dedup / files+pages+chunks / jobs+monitoring+limits / SSE streams / cascade-delete
(no orphans) / negative contract paths (415/413/400/422/404).
