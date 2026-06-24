# DocForge

**Document intelligence platform** — turn any document (PDF, Office, HTML, images…) into a
canonical intermediate representation (IR), enrich it, chunk it, and serve **hybrid retrieval**
(dense + sparse) over it.

> Multi-format → canonical IR → enrichment (OCR/VLM) → structure-aware chunking → BGE-M3
> embeddings in Qdrant → hybrid search + cross-encoder reranking.

---

## Highlights

- **IR is canonical** — Markdown/PDF/HTML are generated *views*, never sources.
- **Every provider is swappable** behind a `Protocol` interface; **URL + secret are per-collection**
  (stored in the DB), never in `.env`.
- **Content-addressed pipeline** with a Merkle-DAG node cache + provider-call cache (re-runs are cheap).
- **Hybrid search** — named dense + sparse vectors in Qdrant, RRF fusion, optional cross-encoder rerank.
- **Collection = contract** — fail-fast validation before any compute is spent.
- Runs **anywhere** — GPU when available, CPU + API fallback (`DeviceManager` centralizes this).

## Stack

| Layer | Choice |
|---|---|
| Runtime | Python 3.12 · FastAPI · Pydantic v2 |
| DB | PostgreSQL 16 (SQLAlchemy 2 async + asyncpg + Alembic) |
| Object store | SeaweedFS (S3-compatible) |
| Workers | arq + Redis |
| Parse | Docling (default), MinerU/Marker, Tika fallback |
| OCR / VLM | PaddleOCR / Mistral OCR · Qwen2.5-VL (vLLM or any OpenAI-compatible API) |
| Embed / rerank | BGE-M3 + BGE-reranker-v2-m3 via the local `bge_server` model host (`src/bge_server`) |
| Vector DB | Qdrant (named dense + sparse) |
| Conversion | Gotenberg (LibreOffice + Chromium) |
| Frontend | React + Vite |
| Containers | Docker + docker compose |

---

## Quickstart

> Requires Docker + docker compose v2.

```bash
# 1. Provision env files from the templates (then edit any secrets)
for s in docforge mcp postgres pgadmin gotenberg redis; do
  cp "services/$s/.env.example" "services/$s/.env"
done

# 2. Build + start the full stack with hot reload
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build -d

# 3. Apply database migrations
docker compose exec docforge sh -c 'cd /app/common && alembic upgrade head'
```

The `bge_server` model service downloads BGE-M3 + the reranker from Hugging Face on first start
(~3 GB) — give it a few minutes; check readiness with `curl http://localhost:10026/health`.

Then open the UI / API:
- API + docs → http://localhost:10020/docs
- Web UI → http://localhost:10023

## Tests

The source tree is multi-root (`src/docforge/{common,app,worker}`); pytest runs from
`src/docforge/` with the deps-only project in `common/`:

```bash
cd src/docforge
# Unit suite — fast, fully mocked, no services needed
uv run --project common pytest tests/units

# Live suite — needs the stack up + the `bge_server` service ready
uv run --project common pytest tests/live_test
```

---

## Repository layout

```
src/
  docforge/
    common/    # shared core (common_libs.*): domain, config, providers, storage, search, pipeline stages
    app/       # FastAPI app (backend.*) — light image, enqueues jobs
    worker/    # arq worker (libs.*) — heavy image (docling), runs the S0→S6 pipeline
    tests/     # unit + live suites + synthetic corpus
  mcp/             # standalone MCP server (DocForge REST surface as MCP tools)
  bge_server/      # local BGE model host (dense + sparse embed + rerank)
services/          # per-service .env (gitignored) + .env.example templates
docker-compose.yml · docker-compose.dev.yml
```

Layer DAG (a layer never imports one above it):
`domain(0) ← config(1) ← providers(1) ← storage(2) ← search(2) ← pipeline(3)`.

## Documentation

- Full design spec → [`SPEC-docforge-document-intelligence-platform.md`](SPEC-docforge-document-intelligence-platform.md)
- API reference → [`docs/api/`](docs/api/)
- Architecture notes → [`docs/metadata-architecture.md`](docs/metadata-architecture.md), [`docs/deployment-resources.md`](docs/deployment-resources.md)

## License

See [`LICENSE`](LICENSE).
