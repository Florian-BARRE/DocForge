# Getting Started with DocForge

DocForge is a document-intelligence platform: it turns any document (PDF, Office, images…) into a
canonical intermediate representation (IR), enriches and chunks it, generates metadata and
embeddings, and serves **hybrid retrieval** (dense + sparse) over it.

This guide takes you from an empty checkout to a running stack and your **first search** — via the
web UI and via `curl`. Every command here is verified against the repository.

---

## 1. Prerequisites

- **Docker** and **Docker Compose v2** (`docker compose`, not the legacy `docker-compose`).
- ~10 GB free disk and ~8 GB RAM available to Docker. The first boot downloads the BGE-M3 embedding
  model and the reranker from Hugging Face (~4–5 GB), so give it a few minutes.
- Open ports in the `10040–10048` range (the stack publishes its dev ports there).
- **GPU is optional and deferred** — the default images build with CPU-only PyTorch. GPU is an
  opt-in override (`docker-compose.gpu.yml`) and is not needed to complete this guide.

No local Python, Node, or Postgres install is required — everything runs in containers.

---

## 2. Clone and configure

```bash
git clone <your-fork-or-repo-url> docforge
cd docforge
```

DocForge reads a handful of `.env` / config files that are **git-ignored**. Provision them from the
committed `.example` templates:

```bash
cp services/docforge/.env.example         services/docforge/.env
cp services/docforge/postgres.env.example services/docforge/postgres.env
cp services/docforge/s3_config.json.example services/docforge/s3_config.json
cp services/bge_server/.env.example              services/bge_server/.env
```

The defaults in these templates work as-is for **local development**. For anything beyond your
laptop you MUST change every password/secret — see [`PROD-HARDENING.md`](PROD-HARDENING.md).

The few values worth knowing about:

| File | Key | What it is |
|---|---|---|
| `services/docforge/postgres.env` | `POSTGRES_PASSWORD` | Postgres password. Must match the password in `POSTGRES_DSN` below. |
| `services/docforge/.env` | `POSTGRES_DSN` | App/worker DB DSN. Keep the host as `localhost:10041` here — Compose overrides it with the in-network hostname when the full stack runs. |
| `services/docforge/.env` | `AUTH_ENABLED` | API-key auth. `false` by default (no credentials needed). See [§6](#6-enabling-api-key-auth). |
| `services/docforge/.env` | `S3_ACCESS_KEY` / `S3_SECRET_KEY` | Blob-store credentials. Any non-empty value works with the local SeaweedFS. |
| `services/docforge/s3_config.json` | `accessKey` / `secretKey` | SeaweedFS S3 identity. For local dev the defaults are fine. |

> **Note:** ML providers (embedding, OCR, VLM, LLM) are **not** configured in `.env`. Their
> `base_url`, API key, and model live **per collection** in the database (in the collection's
> pipeline config). The stock defaults point at the in-stack `bge_server`, so a basic
> ingest + search works out of the box with no external provider.

---

## 3. Start the stack

Start the **full stack** (API + worker + frontend + all stores) with hot reload:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml \
  --profile full up --build -d
```

- **`--profile full` is mandatory.** The app, worker, and frontend live under that profile; without
  it only the backing stores start, and Compose rejects the project with
  `docforge_frontend depends on undefined service docforge_app`.
- The second `-f docker-compose.dev.yml` adds hot reload and **publishes the store ports to
  localhost** (Postgres, Redis, Qdrant, SeaweedFS, bge_server). Production keeps those internal.

### Ports (dev)

| Service | URL / host port |
|---|---|
| **API** (FastAPI) | `http://localhost:10040` |
| **Web UI** (Vite) | `http://localhost:10046` |
| Interactive API docs (Scalar) | `http://localhost:10040/scalar` |
| OpenAPI schema | `http://localhost:10040/openapi.json` |
| Postgres | `localhost:10041` |
| Redis | `localhost:10042` |
| Qdrant (REST) | `localhost:10043` |
| SeaweedFS (S3) | `localhost:10044` |
| Gotenberg (office→PDF) | `localhost:10045` |
| bge_server (embed/rerank) | `localhost:10047` |
| MCP server (streamable-http) | `localhost:10048` |

### Check health

```bash
# API liveness (public, always credential-free — even when auth is on)
curl http://localhost:10040/health
# → {"status":"ok"}

# Embedding server readiness (first boot downloads the models — be patient)
curl http://localhost:10047/health
```

Watch the logs while the models load:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f docforge_bge_server
```

Once both `/health` checks pass, open the web UI at **http://localhost:10046** and the interactive
API reference at **http://localhost:10040/scalar**.

---

## 4. Run database migrations

On first boot, apply the Alembic migrations against the running app container:

```bash
docker compose -f docker-compose.yml exec docforge_app \
  sh -c 'alembic -c /app/shared/alembic.ini upgrade head'
```

Re-run this after pulling changes that add new migrations. (The `env.py` runs async on asyncpg, so
there is no `psycopg2` in the runtime image — always run it through the container.)

---

## 5. First walkthrough — from a collection to a search

A **collection** is the contract: it declares the metadata schema up front and carries the
ingestion pipeline (seeded with the product default when you omit it). You then upload documents
into it, poll the ingestion job, and search.

All API routes below are under the `/api/v1` prefix on `http://localhost:10040`. With
`AUTH_ENABLED=false` (the default) **no `Authorization` header is required** — the `curl` examples
omit it. See [§6](#6-enabling-api-key-auth) to turn auth on.

### Via the web UI

1. Open **http://localhost:10046**.
2. Create a collection: give it a name, the accepted upload extensions (e.g. `pdf`, `txt`, `md`),
   a max file size, and — optionally — a few metadata fields.
3. Upload a document into it.
4. Watch the ingestion job progress through the stages (INTAKE → PARSE → ENRICH → CHUNK →
   CONTEXTUALIZE → METAGEN → EMBED).
5. Once the job is `done`, run a query from the collection's search view.

### Via curl

#### 5.1 Create a collection (with a small metadata schema)

`POST /api/v1/collections`. Omitting `pipeline` seeds the **product-default** graph (all stages
wired), which is what you want for a first run. User-declared metadata fields are document-scoped;
set `filterable: true` to be able to filter searches on them.

```bash
curl -s -X POST http://localhost:10040/api/v1/collections \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "handbook",
    "supported_formats": ["pdf", "txt", "md"],
    "max_file_size_bytes": 26214400,
    "fields": [
      { "field_name": "author",   "field_type": "string", "filterable": true },
      { "field_name": "category", "field_type": "string", "filterable": true,
        "enum_values": ["policy", "guide", "reference"] }
    ]
  }'
```

The response (201) is the full collection contract. Grab its `id`:

```bash
COLLECTION_ID=$(curl -s http://localhost:10040/api/v1/collections \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)[0]["id"])')
echo "$COLLECTION_ID"
```

> Field types are `string · integer · float · bool · keyword_list · datetime`. Metadata fields
> declared here are **fixed at creation** for the vector space — plan the schema up front.

#### 5.2 Upload a document

`POST /api/v1/documents` — a **multipart** form with the file, the target `collection_id`, and an
optional `metadata` JSON object (its keys must exist in the collection's schema). The response is
`202 Accepted` with a `document_id` and a `job_id`.

```bash
# any small local file works; adjust the path + extension to one your collection accepts
curl -s -X POST http://localhost:10040/api/v1/documents \
  -F "file=@./README.md" \
  -F "collection_id=${COLLECTION_ID}" \
  -F 'metadata={"author":"Jane Doe","category":"guide"}'
```

Capture the `job_id`:

```bash
JOB_ID=$(curl -s -X POST http://localhost:10040/api/v1/documents \
  -F "file=@./README.md" \
  -F "collection_id=${COLLECTION_ID}" \
  -F 'metadata={"author":"Jane Doe","category":"guide"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["job_id"])')
echo "$JOB_ID"
```

> Re-uploading the identical file into the same collection with the same pipeline config is a
> no-op: the response has `"duplicate": true` and an empty `job_id`.

#### 5.3 Watch the ingestion job

`GET /api/v1/jobs/{job_id}` returns the live state — `status`, `progress`, `current_stage`, and the
verbatim `error` if it failed.

```bash
curl -s http://localhost:10040/api/v1/jobs/${JOB_ID}
```

Poll until it is done:

```bash
watch -n 2 "curl -s http://localhost:10040/api/v1/jobs/${JOB_ID}"
```

For the per-stage trace, use `GET /api/v1/jobs/{job_id}/events`. To list a collection's jobs:
`GET /api/v1/jobs?collection_id=${COLLECTION_ID}`.

#### 5.4 Run a hybrid search

Once the job reaches `done`, query the collection.
`POST /api/v1/collections/{collection_id}/search`:

```bash
curl -s -X POST http://localhost:10040/api/v1/collections/${COLLECTION_ID}/search \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "how do I get started",
    "limit": 5
  }'
```

The response echoes the query and returns ranked, hydrated chunk hits (`chunk_id`, `document_id`,
`score`, `text`, `chunk_index`, `token_count`).

Refine the search:

```bash
curl -s -X POST http://localhost:10040/api/v1/collections/${COLLECTION_ID}/search \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "installation steps",
    "limit": 10,
    "filters": { "category": "guide" },
    "search_in": [
      { "field": "content", "semantic": true, "lexical": true }
    ]
  }'
```

- `filters` — exact / any-of constraints on **filterable** fields (a scalar is an equality match, a
  list is set membership). Filtering a non-filterable field returns `422`.
- `search_in` — which fields and modalities to query. Omit it to search the chunk body on both
  semantic (dense) and lexical (sparse) axes, the default.

---

## 6. Enabling API-key auth

Auth is **off by default**. When enabled, every `/api/v1/*` route requires a bearer token; the
`/health` probe, the Scalar docs, and `/openapi.json` stay public.

1. In `services/docforge/.env`, set:

   ```dotenv
   AUTH_ENABLED=true
   AUTH_ROOT_TOKEN=<a-strong-secret>
   ```

   The root token is provisioned idempotently at startup as the root account's full-access key.

2. Recreate the app (and worker) so they pick up the new env:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.dev.yml \
     --profile full up -d --force-recreate docforge_app docforge_worker
   ```

3. Every call now needs the header `Authorization: Bearer <token>`:

   ```bash
   curl -s http://localhost:10040/api/v1/collections \
     -H "Authorization: Bearer ${AUTH_ROOT_TOKEN}"
   ```

4. Mint scoped, per-application keys instead of handing out the root token. Keys carry coarse
   capabilities (`read · write · search · admin`) and an optional collection scope. Creating a key
   requires the `admin` capability, and the plaintext is returned **exactly once**:

   ```bash
   curl -s -X POST http://localhost:10040/api/v1/auth/keys \
     -H "Authorization: Bearer ${AUTH_ROOT_TOKEN}" \
     -H 'Content-Type: application/json' \
     -d '{ "name": "search-service" }'
   # → { ..., "key": "df_...", ... }   ← copy it now; it is never shown again
   ```

   Other key-management routes: `GET /api/v1/auth/keys` (list),
   `DELETE /api/v1/auth/keys/{id}` (revoke), `POST /api/v1/auth/keys/{id}/rotate` (rotate).

---

## 7. Next steps

- **[REST API guide](rest-api.md)** — every endpoint with curl examples (and the live reference at
  http://localhost:10040/scalar · schema at `/openapi.json`).
- **[Python SDK guide](python-sdk.md)** — `pip install docforge-sdk`, the typed async + sync client.
- **[MCP server guide](mcp.md)** — drive DocForge from an AI model; the full tool catalogue.
- **[Architecture](architecture.md)** — the graph engine, the 7 stages, packages, retrieval (deep
  reference: [`../src/docforge/PIPELINE.md`](../src/docforge/PIPELINE.md)).
- **[Configuration](configuration.md)** — every environment variable, per service.
- **[Deployment](deployment.md)** — production hardening, ports, secrets, GPU.

Production start (baked images, no dev override, store ports kept internal):

```bash
docker compose -f docker-compose.yml --profile full up -d
```

---

## 8. Troubleshooting

| Symptom | Cause & fix |
|---|---|
| `docforge_frontend depends on undefined service docforge_app` | You dropped `--profile full`. It is **mandatory** — app/worker/frontend live under that profile. |
| Only the stores came up, no app/worker/UI | Same cause — add `--profile full`. |
| Search returns `409 Collection has no embed node` | The collection's pipeline has no embedder wired. Use the default pipeline (omit `pipeline` on create) or add an embed node. |
| Search/upload hangs or 500s on first run | `bge_server` is still downloading models. Wait for `curl http://localhost:10047/health` to return 200. |
| Port already in use on `up` | Another process holds a `10040–10048` port. Free it, or stop a previously running stack: `docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile full down`. |
| `503` from Gotenberg on large office files | Cold LibreOffice spin-up; the API timeout is already raised to 180s — retry, or give the file a moment. |
| DB errors right after first boot | Migrations not applied — run the [§4](#4-run-database-migrations) command. |
| `401` on every `/api/v1/*` call | Auth is on. Send `Authorization: Bearer <token>`, or set `AUTH_ENABLED=false` and recreate the app. |
| Worker marked `unhealthy` | A wedged/hung native call; Docker does not auto-restart on unhealthy. Inspect `docker compose ... logs docforge_worker`. |

To stop and remove the stack (keeping data volumes):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile full down
```

Add `-v` to also delete the volumes (Postgres/Qdrant/SeaweedFS/Redis data and the model cache) —
this wipes everything.
