# DocForge

**Document intelligence platform** — turn any document (PDF, Office, images…) into a canonical
intermediate representation (IR), enrich it, chunk it, and serve **hybrid retrieval** (dense +
sparse) over it.

> Multi-format → canonical IR → enrichment → structure-aware chunking → contextualization →
> generated metadata → BGE-M3 embeddings in Qdrant → hybrid search + optional cross-encoder rerank.

---

## Highlights

- **IR is canonical** — Markdown/PDF/HTML are generated *views*, never sources.
- **Pure graph engine** — a pipeline is a graph of pure nodes (`Config` + `Consume → Produce`, zero
  DB/S3); the worker persists at the edges via the `Database` façade.
- **Provider swappable per family** — the URL + secret live **per collection** (in the DB), never in
  `.env`; a new provider is one more `kind` in its family.
- **Collection = contract** — structural fail-fast at graph build (topology + config shape) before any
  compute is spent.
- **Hybrid search** — named dense + sparse vectors in Qdrant, fusion, optional cross-encoder rerank,
  per-field filterable / semantic / lexical metadata surfaces.
- **API-key auth** — keys-only bearer (authN middleware + per-key authZ scoping); OFF by default.

## Stack

| Layer | Choice |
|---|---|
| Runtime | Python 3.12 · FastAPI · Pydantic v2 · arq + Redis |
| DB | PostgreSQL 16 (SQLAlchemy 2 async + asyncpg + Alembic) |
| Object store | SeaweedFS (S3-compatible, aioboto3) |
| Vector DB | Qdrant (named dense + sparse) |
| Parse | Docling (default; MinerU/Marker escalation ready) |
| OCR / VLM | RapidOCR (local) · Mistral OCR (API) · VLM OpenAI-compatible (Qwen2.5-VL…) |
| Embed / rerank | BGE-M3 + BGE-reranker-v2-m3 via the local `bge_server` host (`src/bge_server`) |
| Conversion | Gotenberg (LibreOffice + Chromium) |
| Frontend | React + Vite |
| Containers | Docker + docker compose |

---

## Quickstart

> Requires Docker + docker compose v2. Firewall opens `10000–11000`.

```bash
# 1. Provision env files from the templates (then edit secrets — see docs/PROD-HARDENING.md for prod)
cp services/docforge-rework/.env.example        services/docforge-rework/.env
cp services/docforge-rework/postgres.env.example services/docforge-rework/postgres.env
cp services/docforge-rework/s3_config.json.example services/docforge-rework/s3_config.json
cp services/bge_server/.env.example             services/bge_server/.env

# 2. Build + start the full stack with hot reload (--profile full is mandatory)
docker compose -f docker-compose.rework.yml -f docker-compose.rework.dev.yml --profile full up --build -d

# 3. Apply database migrations
docker compose -f docker-compose.rework.yml exec rework_app \
  sh -c 'alembic -c /app/shared/alembic.ini upgrade head'
```

`bge_server` downloads BGE-M3 + the reranker from Hugging Face on first start (~few GB) — give it a
few minutes; readiness: `curl http://localhost:10047/health`.

Then open:
- API + docs → http://localhost:10040/scalar
- Web UI → http://localhost:10046

**Prod** (no dev override, baked images, no data-plane ports published):
`docker compose -f docker-compose.rework.yml --profile full up -d` — follow
[`docs/PROD-HARDENING.md`](docs/PROD-HARDENING.md) first.

## Tests

```bash
cd src/docforge-rework
uv run pytest tests/units            # fast, fully mocked, no services needed
uv run pytest -m live                # needs the stack up
uv run ruff check . && uv run mypy . # lint + typecheck
```

---

## Repository layout

```
src/
  docforge-rework/     # THE product (one uv project, 3 roots)
    shared/libs/       #   pure graph engine (pipelines/), public_models/ir, Database façade (services/db)
    app/               #   FastAPI backend (backend.*) + React frontend
    worker/            #   arq worker (runner + IR→DB persistence)
    migrations/        #   Alembic
    tests/units · tests/live
  bge_server/          # local BGE model host (dense + sparse embed + rerank, TEI-compatible)
  mcp/                 # standalone MCP server (pure HTTP client of the DocForge API)
services/              # per-service .env (gitignored) + .env.example templates
docker-compose.rework.yml · docker-compose.rework.dev.yml · docker-compose.rework.gpu.yml
```

Ports (dev): API `10040` · postgres `10041` · redis `10042` · qdrant `10043` · seaweedfs `10044` ·
gotenberg `10045` · frontend `10046` · bge_server `10047`.

## Documentation

- Pipeline (living reference) → [`src/docforge-rework/PIPELINE.md`](src/docforge-rework/PIPELINE.md)
- Full design spec → [`SPEC-docforge-document-intelligence-platform.md`](SPEC-docforge-document-intelligence-platform.md)
- Prod hardening runbook → [`docs/PROD-HARDENING.md`](docs/PROD-HARDENING.md)

## License

See [`LICENSE`](LICENSE).
