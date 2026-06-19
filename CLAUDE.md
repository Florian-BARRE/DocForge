# DocForge — CLAUDE.md

Document intelligence platform: multi-format → IR canonique → enrichissement → chunking → retrieval hybride.
Spec complète : `SPEC-docforge-document-intelligence-platform.md`

---

## Phase courante : P6 — UI React + MCP server ✅ done

| Phase | Statut | Contenu |
|---|---|---|
| **P1** | ✅ done | S0/S1, Postgres + SeaweedFS, Gotenberg, Docling, FastAPI |
| **P2** | ✅ done | Merkle-DAG fingerprints, node cache, provider-call cache, arq workers, dry_run |
| **P3** | ✅ done | S2 classifieur figures, OCR/VLM routing, grounding, chart-to-data, chaînes d'escalade, budget |
| **P4** | ✅ done | S4 chunking structure-aware, S5 contextualisation, S6 BGE-M3 + Qdrant multi-vecteurs |
| **P5** | ✅ done | Collections schema + pipeline update + reindex, hybrid search, chunks router, markdown endpoint |
| **P6** | ✅ done | UI React (workspace unifié, drag-and-drop, live status, recherche hybride) + MCP server |

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
docker-compose.yml        # Production
docker-compose.dev.yml    # Dev overrides (volumes + --reload)
```

> Imports : toujours `from libs.<bucket>.<module> import …` (jamais d'import plat).
> Fichiers >200 lignes = signal de découpage ; quelques exceptions cohésives documentées
> subsistent (ORM models, IR schema, StageEngine orchestrator) avec justification en docstring.

## Règles

- `general.md` : OOP, English, docstrings Google-style, type hints partout
- `python.md` : uv, loggerplusplus, configplusplus, LoggerClass, import order
- `fastapi.md` : CONTEXT, lifespan, `@auto_handle_errors`, structure routers
- `docker.md` : multi-stage, **Docker**, Dockerfiles entièrement commentés en anglais
