# RAG retrieval benchmark (QASPER)

A lightweight, **zero-API-cost** benchmark to check whether DocForge's retrieval is well
parameterised — and specifically whether the **structure-aware chunker** surfaces the right section
of a long document.

## Two corpora, two questions
- **`qasper`** (default) — QA over **full scientific papers**: long, explicitly **sectioned**
  documents, each question shipping the gold **evidence paragraph(s)**. Sections are large, so it
  measures **retrieval quality** end-to-end (parse → structure-aware chunk → hybrid retrieve → does a
  retrieved chunk *cover* the evidence). Its sections are almost all >64 tokens, so it does **not**
  discriminate chunk granularity (default `min_tokens=64` never coalesces anything → default ≈ strict).
- **`regulatory`** — a **synthetic** stack of short single-clause articles (~20 tokens each), generated
  deterministically (no network, no API). This is the shape that makes the chunker's granularity knob
  **matter**: under the default a handful of neighbouring clauses coalesce into one chunk, under strict
  (`min_tokens=0`) every clause stays its own chunk. Same clause topics recur across several regulations
  with different values, so a query must resolve to the **right document's** clause — the cross-file
  disambiguation a real regulatory RAG faces. Use it to answer *"default vs strict chunking — which
  retrieves better on short-section docs?"*

(BEIR-style passage benchmarks are 1 chunk/doc and test neither.)

## Cost & footprint
- Runs on the **default pipeline**: docling + structure-aware chunk + doc_meta/breadcrumb context +
  **BGE-M3 dense+sparse (local)**. Enrich (VLM) and metagen (LLM) stay OFF → **no paid API, 0 €**.
- The dataset is pulled page-by-page from the HuggingFace datasets-server HTTP API (no `datasets`
  dependency) and cached under `data/` (git-ignored). A slice of ~150 papers is plenty.

## Layout
- `metrics.py` — pure retrieval metrics (coverage, hit@k, recall@k, MRR). **Unit-tested, no stack.**
- `qasper.py` — QASPER loader + HTML rendering (headings per section) + evidence extraction.
- `synthetic.py` — the deterministic short-clause **regulatory** corpus (pure, unit-tested).
- `harness.py` — thin REST client + the eval loop (`run_eval`, `compare_configs`, `client_from_env`).
- `runner.py` — CLI: run/compare chunk configs against the live stack and print hit@k + MRR.
- `test_metrics.py`, `test_synthetic.py` — unit tests (`python -m pytest tests/rag_eval/test_*.py`).
- `test_rag_eval_live.py` — a `live`-marked smoke test (tiny end-to-end against the running stack).
- `data/` — **git-ignored** cache of downloaded rows.

## Run it

Unit tests (no stack, no network):
```bash
cd src/docforge && uv run pytest tests/rag_eval/test_metrics.py
```

Live smoke (stack up; a few papers):
```bash
export DOCFORGE_TOKEN=$(docker compose -f compose/dev-cpu.yml \
  exec -T docforge_app printenv AUTH_ROOT_TOKEN | tr -d '\r')
cd src/docforge && uv run pytest tests/rag_eval/test_rag_eval_live.py -m live -s
```

Chunk sweep — retrieval quality on real papers (default vs strict, big sections → same result):
```bash
export DOCFORGE_TOKEN=$(docker compose -f compose/dev-cpu.yml \
  exec -T docforge_app printenv AUTH_ROOT_TOKEN | tr -d '\r')
cd src/docforge && uv run python -m tests.rag_eval.runner --corpus qasper --papers 8 --sweep
```

Chunk sweep — the one that actually diverges (short-clause synthetic regulations):
```bash
cd src/docforge && uv run python -m tests.rag_eval.runner --corpus regulatory --papers 6 --sweep
```

Each run **purges** prior benchmark collections (name prefix `🔬 BENCH · `) and creates fresh, clearly
named ones: `🔬 BENCH · <corpus> · <config> · <n> docs`.

Env: `DOCFORGE_API_BASE` (default `http://localhost:10040/api/v1`), `DOCFORGE_TOKEN` (required).

## Reading the numbers
- **hit@k** — fraction of questions whose gold evidence appears in the top-k retrieved chunks.
- **MRR** — mean reciprocal rank of the first covering chunk.
- The `--sweep` compares `min_tokens=64` (default, coalesces tiny sections) vs `min_tokens=0` (strict
  one section = one chunk). Higher hit@k / MRR = better retrieval for that config on this corpus.
