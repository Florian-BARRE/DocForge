# DocForge — CLAUDE.md

Plateforme de document intelligence : multi-format → **IR canonique** → enrichissement → chunking →
contextualisation → métadonnées générées → embeddings → **retrieval hybride**.
Spec complète : `SPEC-docforge-document-intelligence-platform.md`
Pipeline (doc vivante, LA référence) : `src/docforge-rework/PIPELINE.md`

---

## Arbre de code unique

**`src/docforge-rework/`** est LE produit — moteur graphe v2, stage-rail studio. L'ancien produit
legacy (moteur statique S0→S6, `src/docforge/`) a été **supprimé**. Reste une seule étape de
migration : renommer `src/docforge-rework/` → `src/docforge/` (et les composes `.rework.*`).

---

## Commandes — stack rework (par défaut)

- **Dev (hot reload)** : `docker compose -f docker-compose.rework.yml -f docker-compose.rework.dev.yml --profile full up --build -d` — `--profile full` est **obligatoire** : app/worker/frontend sont sous `profiles: ["full"]` (sans lui seuls les stores démarrent, et le compose rejette `rework_frontend depends on undefined service rework_app`).
- **Prod** : `docker compose -f docker-compose.rework.yml --profile full up -d`
- **Tests unitaires** : `cd src/docforge-rework && uv run pytest tests/units` (projet uv autonome, tout mocké)
- **Un seul test** : `uv run pytest tests/units/engine/test_x.py::TestClass::test_method` (`-x`, `-k <expr>`)
- **Tests live** (stack up requise) : `uv run pytest -m live`
- **Lint / typecheck** : `uv run ruff check .` (+ `ruff format .`) et `uv run mypy .`
- **Frontend TS (gate)** : `docker compose -f docker-compose.rework.yml -f docker-compose.rework.dev.yml exec rework_frontend sh -c 'cd /frontend && npx tsc --noEmit && npm run build'` — node_modules est **container-side** (volume `rework_frontend_modules`) ; le stub host root-owned est un simple point de montage Docker, jamais `npm install` côté host.
- **Migrations** : `docker compose -f docker-compose.rework.yml exec rework_app sh -c 'alembic -c /app/shared/alembic.ini upgrade head'` (env.py tourne en async sur asyncpg — pas de psycopg2 dans l'image runtime).
- **Ports dev** : API `10040` · postgres `10041` · redis `10042` · qdrant `10043` · seaweedfs `10044` · gotenberg `10045` (firewall VM : `10000–11000`).

---

## Principes non négociables

<important>
1. **L'IR est canonique** — markdown/PDF/HTML sont des vues générées, jamais sources.
2. **Pipeline PURE** — un node = `Config` + `Consomme → Produit`, **zéro DB/S3**. Le worker persiste
   aux bords via la façade `Database` ; le contrat de collection arrive en **run input**.
3. **Provider interchangeable dans sa famille** — URL + secret **par collection** (en DB), jamais en `.env`.
4. **Collection = contrat** — fail-fast **structurel** au **build du graphe** (topologie + forme de config)
   avant toute dépense. ⚠️ La **connectivité** (URL/clé joignables) n'est **PAS** vérifiée au build : un
   `base_url`/`api_key` faux construit proprement et échoue au **run** (un `preflight()` par node reste à faire).
5. **Config `extra="forbid"`** — un typo dans le blob fait **échouer le build**, jamais ignoré silencieusement.
6. **Vecteur maigre** — seuls les champs filtrables dans Qdrant ; le riche est en Postgres.
7. **`DeviceManager` centralise GPU/CPU** — aucune logique device dans les nodes.
</important>

---

## Architecture — le moteur graphe (v2)

**7 étapes** : `INTAKE → PARSE → ENRICH → CHUNK → CONTEXTUALIZE → METAGEN → EMBED`.
Détail complet des étapes, nodes, artefacts et décisions → **`PIPELINE.md`**. Mécanique du graphe :

- **Transitions** (contrôle) : `OnSuccess` (défaut) · `OnFailure` (recovery/escalade) ·
  `ScoreBelow(seuil)` (escalade qualité) · `WhenEquals(field, val)` (le switch) · `Always`.
  **Priorité** : `ScoreBelow > WhenEquals > OnSuccess/OnFailure > Always`.
- **Bindings** (données) : `FromRunInput` · `FromNode(node, field)` (n'importe quel amont) ·
  `FromGroupInput` · `FromFirst(candidats)` (jointure après embranchement). Slots typés (`Artifact` ou `list[Artifact]`).
- **`ForEach`** : sous-graphe par item (`over` / `item_field` / `max_concurrency`) ; tous les terminaux
  produisent le MÊME `Artifact` → `items: list[T]`.
- **Familles** (palette UI, kinds sans redondance) : `intake · converter · parser · render · enrich ·
  chunker · contextualize · metagen` + capacités génériques `embed · ocr · vlm · llm`.
- **`UNIQUE_IN_GRAPH`** : rejette une 2e instance d'un kind single-use au build (`duplicate_unique_node`).

---

## Structure — `src/docforge-rework/` (3 racines, un projet uv)

```
shared/libs/                 # SOCLE PARTAGÉ — importé via l'alias `shared_libs`
  pipelines/                 #   LE MOTEUR PUR : base/ (node·graph·transition·slots·io·foreach·group)
                             #     engine/ (core·resolver·progress) · edit/ (GraphEditor) · validation/ (GraphValidator)
    nodes/                   #     capacités génériques : llm · ocr · vlm · embed · openai_compat (factory partagée)
    ingest/                  #     LA pipeline : nodes/ groupés par étape · stages/ (StageCompiler) · build/ (PipelineBuilder)
  public_models/ir/          #   DocumentIR + artefacts publics (SourceDocument, Chunk, EnrichmentEntry…)
  services/db/               #   façade `Database` → facades/ (auth·collections·documents·ingestion·jobs·metagen·search)
                             #     + clients postgresql/ (apis + tables SQLAlchemy) · qdrant/ · s3/
app/                         # APP FASTAPI + FRONTEND
  backend/routers/           #   pipelines · collections · documents · explorer · jobs · blobs · scalar
  frontend/                  #   React (features/ · shell/ routing maison) — stage-rail UI + API headless
  config/                    #   RUNTIME_CONFIG ; register_package_alias(`shared_libs`) + backend/libs sur sys.path
worker/                      # WORKER ARQ
  backend/libs/              #   runner/ (exécute la pipeline pure) · persistence/ (translator IR→DB) · jobs/ (core·progress)
migrations/ · shared/migrations/   # Alembic
tests/units/{api,edit,engine,nodes,stages,validation,worker} · tests/live
```

> **Imports** : `from shared_libs.<x> import …`. Le `sys.path` est câblé par le `config` de chaque app
> (`RuntimePathHelpers` : `register_package_alias` + `add_to_python_path`), donc **`config` (donc `RUNTIME_CONFIG`)
> s'importe en PREMIER** dans chaque entrypoint. En test, `tests/conftest.py` installe l'alias `shared_libs`
> **une seule fois** (le `NodeRegistry` est un état global process — un double alias casserait).

---

## Stack

| Couche | Choix |
|---|---|
| Runtime | Python 3.12 · FastAPI · Pydantic v2 · **arq + Redis** (worker) |
| DB | PostgreSQL 16 (SQLAlchemy 2 async + asyncpg + Alembic) |
| Object store | SeaweedFS (aioboto3, S3-compat) · **Qdrant** (named dense + sparse) |
| Parse | Docling (défaut ; MinerU/Marker en escalade prête) |
| OCR / VLM | RapidOCR (local) · Mistral OCR (API) · VLM OpenAI-compat (Qwen2.5-VL…) |
| Embed | **BGE-M3** via `src/bge_server` (dense+sparse) ou tout endpoint OpenAI-compat (dense) |
| Conversion | Gotenberg (LibreOffice + Chromium) |
| Hash | sha256 (content-addressing) · blake3 (fingerprints de cache) |
| Conteneurs | **Docker + docker compose** |

---

## Composants voisins (hors `docforge-rework/`)

- `src/bge_server/` — serveur local BGE-M3 (embed dense+sparse + rerank, TEI-compatible).
- `src/mcp/` — MCP standalone, **client HTTP pur** de l'API DocForge (aucun import domaine).

---

## Règles (`.claude/rules/`)

- `architecture.md` : moteur graphe (nodes/edges/foreach/validation) + les 3 racines — cheat-sheet pour éditer la pipeline
- `general.md` : OOP, English, docstrings Google-style, type hints partout
- `python.md` : uv, loggerplusplus, configplusplus, LoggerClass, import order
- `fastapi.md` : CONTEXT, lifespan, `@auto_handle_errors`, structure routers
- `docker.md` : multi-stage, Dockerfiles commentés en anglais
- `orchestrator.md` : routing des agents spécialisés (toujours chargée)

> Historique des phases de l'ancien produit → `docs/archive/phases-legacy.md`.
> Fichiers >200 lignes = signal de découpage.
