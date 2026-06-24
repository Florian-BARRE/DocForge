# DocForge — CLAUDE.md

Document intelligence platform: multi-format → IR canonique → enrichissement → chunking → retrieval hybride.
Spec complète : `SPEC-docforge-document-intelligence-platform.md`

---

## Phase courante : P7 — Search pipeline engine ✅ done

| Phase | Statut | Contenu |
|---|---|---|
| **P1** | ✅ done | S0/S1, Postgres + SeaweedFS, Gotenberg, Docling, FastAPI |
| **P2** | ✅ done | Merkle-DAG fingerprints, node cache, provider-call cache, arq workers, dry_run |
| **P3** | ✅ done | S2 classifieur figures, OCR/VLM routing, grounding, chart-to-data, chaînes d'escalade, budget |
| **P4** | ✅ done | S4 chunking structure-aware, S5 contextualisation, S6 BGE-M3 + Qdrant multi-vecteurs |
| **P5** | ✅ done | Collections schema + pipeline update + reindex, hybrid search, chunks router, markdown endpoint |
| **P6** | ✅ done | UI React (workspace unifié, drag-and-drop, live status, recherche hybride) + MCP server |
| **P7** | ✅ done | SearchPipelineEngine : query transform (rewrite/HyDE/multi_query) + cross-encoder reranking (BGE/Cohere) |

> Phase file inventory and key decisions per phase → `.claude/rules/phases.md`

---

## Principes non négociables

1. **L'IR est canonique** — markdown/PDF/HTML sont des vues générées, jamais sources.
2. **Tout provider est interchangeable** derrière une interface `Protocol`.
3. **`DeviceManager` centralise GPU/CPU** — aucune logique device dans les briques.
4. **Locality gate** — résolution à 3 niveaux : locality → provider → device.
5. **Vecteur maigre** — seuls les champs filtrables dans Qdrant ; le riche est en Postgres.
6. **Collection = contrat** — validation fail-fast avant toute dépense.

---

## Architecture

```
REST API (FastAPI) ──→ arq workers (P2+)
                              ↓
                    Stage engine (DAG + double cache P2+)
                    S0 ─→ S1 ─→ S2 ─→ S3 ─→ S4 ─→ S5 ─→ S6
                              ↓                    ↓
                         Postgres 16           SeaweedFS/S3
                         (source of truth)     (blobs content-addressed)
                                                    ↓
                                              Qdrant (P4+)
```

## Stack

| Couche | Choix |
|---|---|
| Runtime | Python 3.12 + FastAPI + Pydantic v2 |
| DB | PostgreSQL 16 (SQLAlchemy 2 async + asyncpg + Alembic) |
| Object store | SeaweedFS (aioboto3, S3-compat) |
| Workers | arq + Redis (P2) |
| Parse | Docling (défaut), MinerU/Marker (routés, P3+), Tika (fallback couverture) |
| OCR | olmOCR-2/PaddleOCR (GPU), Mistral OCR API (CPU+API) |
| VLM | Qwen2.5-VL via vLLM (local) ou toute API OpenAI-compat |
| Embed | BGE-M3 (TEI GPU / ONNX CPU) |
| Vector DB | Qdrant (named dense + sparse BM25) |
| Conversion | Gotenberg (LibreOffice + Chromium, HTTP API) |
| Hash | blake3 (fingerprints), sha256 (content-addressing) |
| Conteneurs | **Docker + docker compose** |

## GPU Strategy

Serveur-agnostique : GPU (CUDA 11.8, V100) quand disponible, fallback CPU+API.
`DeviceManager` gère la détection — jamais dans les providers individuels.

---

## Structure du projet

Code éclaté en **3 racines sous `src/`** (+ le MCP), selon qui consomme quoi. DAG strict :
`domain(0) ← config(1) ← providers(1) ← storage(2) ← search(2) ← pipeline(3)`.
Règle d'or : une couche n'importe jamais une couche au-dessus d'elle.

```
src/
  docforge/                 # LE PRODUIT : app + worker + socle commun (travaillent ensemble)
    common/                 # SOCLE PARTAGÉ — chargé par app ET worker
      pyproject.toml        #   contrat de deps (deps-only) + uv.lock ; `--extra worker` = docling
      base_config/          #   BaseRuntimeConfig (vars communes + setup logging) — hérité par les 2 apps
      common_libs/          #   importé `from common_libs.<bucket> import …`
        domain/             #     L0 — modèles purs (IR, Chunk, metadata)
        config/             #     L1 — PipelineConfig, validation, admission
        providers/          #     L1 — capacités ML (converter/parser/ocr/vlm/embed/rerank/llm/device…)
        storage/            #     L2 — postgres/ + qdrant/ + s3/
        search/field_index/ #     L2 — schéma de champs (partagé : S6 + query)
        observability/      #     events/ + heartbeat/ (partagés)
        pipeline/           #     L3 — caches/, assembly/ (registry), stages/ (S0–S6)
    app/                    # APP FASTAPI — image légère (sans docling)
      Dockerfile  entrypoint.py  alembic.ini  migrations/
      config/               #   RUNTIME_CONFIG(BaseRuntimeConfig) + vars web (FASTAPI/CORS/SSE/ADMISSION)
      backend/              #   app, CONTEXT, lifespan, routers (+ backend/libs : error_handling, sse, admission)
      libs/                 #   dédié `from libs.<x>` : search/{hybrid,metadata_indexer,pipeline}, observability/queue
      frontend/             #   React + Vite (dist/ servi en statique)
    worker/                 # WORKER ARQ — image lourde (+ docling)
      Dockerfile  arq_worker.py
      config/               #   RUNTIME_CONFIG(BaseRuntimeConfig) + vars worker (WORKER_*, OBS_METRICS)
      libs/                 #   dédié `from libs.<x>` : pipeline/{engine,orchestrator,worker}, observability/metrics
    tests/                  # tests docforge (app + worker testés ensemble)
  mcp/                      # MCP standalone (client HTTP pur, aucun import domaine)
  embedding_server/         # serveur d'embedding BGE-M3 (TEI-compatible)
services/                   # .env par service (docforge, postgres, seaweedfs, gotenberg, redis, pgadmin)
docker-compose.yml          # Prod (app→docforge/app/Dockerfile, worker→docforge/worker/Dockerfile)
docker-compose.dev.yml      # Dev overrides (volumes common+app + --reload)
```

> Conso ressources & plafonds CPU/RAM par service → `docs/deployment-resources.md`

### Deux apps, un socle : `common_libs.*` vs `libs.*` (+ config par héritage)

`base_config` + `common_libs.*` (dans `src/docforge/common/`) = **socle partagé**, chargé par les DEUX
apps. Chacune a en plus son `config` (`RUNTIME_CONFIG(BaseRuntimeConfig)` + vars dédiées) et son `libs.*`
**dédié** (sous `src/docforge/app/` ou `src/docforge/worker/`), résolus par app au runtime.
`entrypoint.py` / `arq_worker.py` bootstrappent `sys.path` (`docforge/common` + leur dossier) avant
d'importer `config`. Import partagé → `from common_libs.<bucket> import …` ; dédié → `from libs.<x> import …`.

| Racine | Modules | Lancé par |
|---|---|---|
| `docforge/common/` (`common_libs.*` + `base_config`) | domain, config, providers, storage, observability events/heartbeat, search/field_index, pipeline caches/assembly/**stages** | les deux |
| `docforge/app/` (`config` + `libs.*`) | search hybrid/metadata_indexer/pipeline, observability/queue + le package `backend/` | uvicorn |
| `docforge/worker/` (`config` + `libs.*`) | pipeline engine/orchestrator/worker, observability/metrics | arq |

> Les **stages** (S0→S6) vivent en `common_libs` (pas en worker) car le registry partagé
> (`pipeline/assembly`) les importe **statiquement**. L'app ne lance jamais l'ingestion : elle enqueue
> un job, le worker l'exécute. Image app ~2-3 GB plus légère (docling = `--extra worker`).
> `RUNTIME_CONFIG` **hérite** de `BaseRuntimeConfig` : le commun ne porte QUE les vars lues par les libs
> partagées ; web-only (FASTAPI/SSE/ADMISSION) et worker-only (WORKER_*/OBS_METRICS) vivent côté app/worker.
> Fichiers >200 lignes = signal de découpage ; exceptions cohésives documentées en docstring.

## Règles

- `general.md` : OOP, English, docstrings Google-style, type hints partout
- `python.md` : uv, loggerplusplus, configplusplus, LoggerClass, import order
- `fastapi.md` : CONTEXT, lifespan, `@auto_handle_errors`, structure routers
- `docker.md` : multi-stage, **Docker**, Dockerfiles entièrement commentés en anglais
