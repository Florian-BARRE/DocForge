# RAG retrieval benchmark (QASPER)

A lightweight, **zero-API-cost** benchmark to check whether DocForge's retrieval is well
parameterised — and specifically whether the **structure-aware chunker** surfaces the right section
of a long document.

## Why QASPER
QASPER is QA over **full scientific papers**: each document is long and explicitly **sectioned**, and
every question ships the gold **evidence paragraph(s)** that answer it. So it exercises the whole
chain — parse → structure-aware chunk → hybrid retrieve — and lets us measure whether a retrieved
chunk *covers* the evidence. (BEIR-style passage benchmarks are 1 chunk/doc and do **not** test
chunking.)

## Cost & footprint
- Runs on the **default pipeline**: docling + structure-aware chunk + doc_meta/breadcrumb context +
  **BGE-M3 dense+sparse (local)**. Enrich (VLM) and metagen (LLM) stay OFF → **no paid API, 0 €**.
- The dataset is pulled page-by-page from the HuggingFace datasets-server HTTP API (no `datasets`
  dependency) and cached under `data/` (git-ignored). A slice of ~150 papers is plenty.

## Layout
- `metrics.py` — pure retrieval metrics (coverage, hit@k, recall@k, MRR). **Unit-tested, no stack.**
- `qasper.py` — dataset loader + HTML rendering (headings per section) + evidence extraction.
- `harness.py` — thin REST client + the eval loop (`run_eval`, `compare_configs`, `client_from_env`).
- `runner.py` — CLI: run/compare chunk configs against the live stack and print hit@k + MRR.
- `test_metrics.py` — unit tests (`uv run pytest tests/rag_eval/test_metrics.py`).
- `test_rag_eval_live.py` — a `live`-marked smoke test (tiny end-to-end against the running stack).
- `data/` — **git-ignored** cache of downloaded rows.

## Run it

Unit tests (no stack, no network):
```bash
cd src/docforge && uv run pytest tests/rag_eval/test_metrics.py
```

Live smoke (stack up; a few papers):
```bash
export DOCFORGE_TOKEN=$(docker compose -f docker-compose.yml -f docker-compose.dev.yml \
  exec -T docforge_app printenv AUTH_ROOT_TOKEN | tr -d '\r')
cd src/docforge && uv run pytest tests/rag_eval/test_rag_eval_live.py -m live -s
```

Full benchmark + chunk sweep (default vs strict one-chunk-per-section):
```bash
export DOCFORGE_TOKEN=$(docker compose -f docker-compose.yml -f docker-compose.dev.yml \
  exec -T docforge_app printenv AUTH_ROOT_TOKEN | tr -d '\r')
cd src/docforge && uv run python -m tests.rag_eval.runner --papers 150 --sweep
```

Env: `DOCFORGE_API_BASE` (default `http://localhost:10040/api/v1`), `DOCFORGE_TOKEN` (required).

## Reading the numbers
- **hit@k** — fraction of questions whose gold evidence appears in the top-k retrieved chunks.
- **MRR** — mean reciprocal rank of the first covering chunk.
- The `--sweep` compares `min_tokens=64` (default, coalesces tiny sections) vs `min_tokens=0` (strict
  one section = one chunk). Higher hit@k / MRR = better retrieval for that config on this corpus.
