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

`libs/` est rangé **par domaine**, 6 buckets. DAG strict des couches :
`domain(0) ← config(1) ← providers(1) ← storage(2) ← search(2) ← pipeline(3)`.
Règle d'or : une couche n'importe jamais une couche au-dessus d'elle.

```
src/docforge/             # Source app (dans WORKDIR /app/docforge)
  entrypoint.py           # uvicorn target: uvicorn entrypoint:app
  arq_worker.py           # arq target: arq arq_worker.WorkerSettings
  mcp_server.py           # MCP server (client HTTP, aucun import domaine)
  config/runtime/         # RUNTIME_CONFIG (EnvConfigLoader) — sys.path.append(PATH_ROOT_DIR)
  libs/
    domain/               # L0 feuille — modèles purs (IR, Chunk, metadata)
      ir/                 #   IR Pydantic + sérialisation markdown
      metadata/           #   schéma de champs (MetaFieldSpec, system fields)
    config/               # L1 — tout ce qui est config
      pipeline/           #   PipelineConfig, _registry, spec_utils, stage configs
        stages/           #   parse/enrich/chunk/contextualize/embed configs
      validation/         #   ConfigValidator + explain (ex-governance/config_validation)
      admission/          #   AdmissionValidator (ex-governance/admission)
    providers/            # L1 — capacités ML interchangeables : interfaces Protocol,
                          #      chain, device, converter/parser/ocr/vlm/embed/classifier/lang
    storage/              # L2 — persistance brute
                          #      postgres/ (SQLAlchemy) + qdrant/ + s3/ (aioboto3)
    search/               # L2 — recherche & indexation
                          #      hybrid/ (HybridSearchService), field_index/, metadata_indexer/
    pipeline/             # L3 — orchestration pipeline
                          #      engine.py (StageEngine), orchestrator/, assembly/,
                          #      stages/ (S0–S6, each a folder with core/helpers/result),
                          #      caches/ (fingerprint/node/provider), worker/ (runner/tasks)
  backend/                # FastAPI app, CONTEXT, lifespan, routers (+ backend/libs/utils)
  migrations/             # Alembic
services/                 # .env par service (docforge, postgres, seaweedfs, gotenberg, redis)
docker-compose.yml        # Production (+ deploy.resources.limits par service)
docker-compose.dev.yml    # Dev overrides (volumes + --reload)
```

> Conso ressources & plafonds CPU/RAM par service → `docs/deployment-resources.md`

> Imports : toujours `from libs.<bucket>.<module> import …` (jamais d'import plat).
> Fichiers >200 lignes = signal de découpage ; quelques exceptions cohésives documentées
> subsistent (ORM models, IR schema, StageEngine orchestrator) avec justification en docstring.

### `libs/` = socle commun à deux consommateurs

`libs/` n'appartient ni au backend ni au worker : c'est leur **socle partagé** (le « common »).
Deux points d'entrée le consomment — `entrypoint.py` (backend FastAPI) et `arq_worker.py` (worker arq).
C'est pourquoi `libs/` est leur **frère**, jamais rangé sous `backend/` (sinon le worker dépendrait du
web sans raison). Zones d'usage réelles :

| Zone | Modules | Lancé par |
|---|---|---|
| **Backend-only** (web/query) | `search/hybrid`, `search/metadata_indexer`, `observability/queue`, `backend/libs/` (error_handling, sse, admission) | uvicorn |
| **Worker-only** (ingestion) | `pipeline/engine`, `pipeline/orchestrator`, `pipeline/worker/`, exécution des stages `pipeline/stages/` (S0→S6), `observability/metrics` | arq |
| **Partagé** (le socle) | `domain`, `config`, `providers` (+ `pipeline/assembly` registry), `storage`, `pipeline/caches`, `observability/events`+`heartbeat`, `search/field_index` | les deux |

> Le backend ne lance **jamais** le pipeline d'ingestion S0→S6 : il enqueue un job, le worker l'exécute.
> Le registry (`pipeline/assembly`) câble dynamiquement providers + stages → il tire l'essentiel du socle,
> ce qui rend une scission physique backend/worker/common peu rentable (le partagé est majoritaire).

## Règles

- `general.md` : OOP, English, docstrings Google-style, type hints partout
- `python.md` : uv, loggerplusplus, configplusplus, LoggerClass, import order
- `fastapi.md` : CONTEXT, lifespan, `@auto_handle_errors`, structure routers
- `docker.md` : multi-stage, **Docker**, Dockerfiles entièrement commentés en anglais
