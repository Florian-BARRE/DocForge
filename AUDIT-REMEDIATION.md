# DocForge — Remédiation de l'audit v0.14.0

> Chantier de mise à plat suite à l'audit du 2026-09-04 (`main @ 0162c70`). Rapport complet: https://claude.ai/code/artifact/1f51943f-6e30-4e4f-9906-ceca159cb457

**247 points uniques** — 25 haute · 107 moyenne · 115 faible. Traités par vague, par ordre de sévérité. `[ ]` à faire · `[x]` fait · `[~]` en cours.

> Branche : `fix/audit-remediation`. Les buckets de vague ci-dessous sont indicatifs (heuristiques) ; la séquence V1→V8 faisant autorité est celle du rapport. Chaque tranche est commitée + vérifiée (ruff + pytest units) avant de passer à la suivante.

## Journal

- **2026-09-04 — V1 tranche 1 (backend authz)** : IDOR `PATCH /documents/{id}/enabled` + `POST /documents/{id}/reingest` fermés (chargement du document → `assert_collection_scope` avant toute mutation/dépense) ; `GET /collections` filtré par `scoped_collections` (plus de fuite de contrat inter-tenant). +3 tests de non-régression (scoped key → 403 / liste filtrée). `532 passed`.

- **2026-09-04 — V1 tranche 2 (import .dcexport)** : écrasement S3 arbitraire fermé — l'import épingle désormais chaque blob à son `content_hash` (invariant content-addressed) au lieu de faire confiance au `s3_key` du bundle ; un `s3_key` falsifié pointant sur l'objet d'un autre tenant est ignoré + loggé. +1 test tamper. `26 passed`.

- **2026-09-04 — V1 tranche 3 (fuite creds au boot)** : `ConfigDumpHelpers.masked` (nouveau, `shared_libs.observability`) rédige le userinfo `://user:pass@` de toute URL/DSN au dump de démarrage — `POSTGRES_DSN`/`REDIS_URL` ne fuitent plus en clair (stdout + Loki) ; le masquage par nom de configplusplus est préservé. Câblé sur les 2 lifespans (app+worker). +5 tests. `verts`.

- **2026-09-04 — V1 tranche 4 (XSS blob, HAUTE+MOYENNE)** : `openBlobInNewTab` n'ouvre inline que les types inertes (PDF/images) — HTML/SVG/texte → download, plus de rendu `blob:` same-origin ; `GET /blobs/{hash}` ajoute `nosniff` (tout blob) + `attachment`+`CSP sandbox` (types non inertes). +8 tests headers. **Validé E2E par agent dédié sur la stack live** (HTML→attachment+sandbox+nosniff ; PDF→inline+nosniff). tsc/lint verts.

- **2026-09-04 — V1 tranche 5 (import → CREATE)** : `POST /collections/import` gaté sur `Capability.CREATE` (comme `POST /collections`) au lieu de `WRITE` — une clé WRITE-only ne peut plus escalader en création de collection via un import. +1 test de contrat du gate. Reste (tracké `[~]`) : le grant de scope au créateur (clé scoped CREATE) nécessite un threading queue→worker, slice dédié. `19 passed`.

- **2026-09-04 — V1 tranche 6 (MCP file_path, HAUTE)** : nouveau `PathGuard` (`src/mcp/libs/path_guard.py`) — sur le transport streamable-HTTP, `file_path` de `upload_document`/`import_collection` doit résoudre (symlinks suivis) DANS `MCP_UPLOAD_DIR` sinon refusé avant tout appel SDK ; défaut fail-closed (pas d'inbox → refusé). stdio inchangé. Knob `MCP_UPLOAD_DIR` documenté (docs/mcp.md). Impl par agent `mcp` dédié, finalisée+vérifiée : `42 passed`, ruff+mypy clean. **→ tous les 7 findings HAUTE de V1 sont fermés.**

- **2026-09-04 — V1 tranche 7 (decompression bomb)** : l'extraction d'un `.dcexport` borne désormais la taille décompressée (`ratio × taille_compressée`, knob `IMPORT_MAX_DECOMPRESSION_RATIO`=100) ET le nombre de membres (`IMPORT_MAX_MEMBERS`=500k) — un bundle à ratio >1000x est refusé en cours d'extraction avant de remplir le disque. +3 tests (bomb taille/membres refusée, extraction normale OK). Reste (`[~]`) : le buffering mémoire de tous les blobs à l'import (batching), slice dédié. `33 passed`.

- **2026-09-04 — V1 tranche 8 (port Gotenberg)** : le publish `10045:3000` retiré de `compose/base.yml` (donc plus exposé en **prod** — Gotenberg = API de conversion non-auth, pivot SSRF) et déplacé dans `compose/overlays/dev.yml` (comme les stores) ; les collections l'atteignent via l'alias réseau `gotenberg:3000`. `docs/configuration.md` aligné. Validé : prod-cpu = 0× 10045, dev-cpu = publié, tous scénarios×add-ons `config -q` OK.

- **2026-09-04 — V1 tranche 9 (creds postgres fresh-clone)** : les 3 sources alignées sur `docforge` — `postgres.env.example` (bootstrap DB), `.env.example` (DSN host-side), et le fallback compose `docforge:docforge` concordent → un clone propre boote sans erreur d'auth ; bloc `POSTGRES_DSN` commenté ajouté au `.env` racine (mécanisme d'override prod, absent avant) + avertissements change-me. Vérifié : 0 `change_me` résiduel.

- **2026-09-04 — V1 tranche 10 (paddle body-cap)** : `/ocr` et `/layout-parsing` lisent le corps sous un plafond dur (`RequestBodyGuard.read_capped` : Content-Length > cap → 413 avant lecture, puis stream capé contre un length menteur/absent) ; knob `PADDLE_MAX_BODY_BYTES` (100 MiB) documenté. +5 tests guard + wiring adapté. Gate paddle : 32 tests, ruff+mypy clean.

- **2026-09-04 — V1 tranche 11 (SSRF egress allowlist)** : `ProviderEgressPolicy` (pur, allow-all par défaut, globs+CIDR) + knob `PROVIDER_EGRESS_ALLOWLIST` (app+worker, OFF par défaut) enforcé à 2 edges — le **health sweep** (un host non listé → `blocked`, jamais sondé : plus de scanner) et le **preflight worker** (refus avant la 1re dépense) ; couvre l'oracle ingest ET search. Runtime in-node : documenté honnêtement (repose sur preflight + egress réseau). Impl core par agent `pipeline` dédié, **finalisée par moi** (wiring worker jobs/core, +16 tests policy/sweep, doc PROD-HARDENING §7). 300 passed, ruff clean.

- **2026-09-04 — V2 tranche 1 (SSE CANCELLED)** : le stream SSE d'un job fermait uniquement sur `{done,failed}` — un job CANCELLED (3e état terminal, non écrasable) faisait poller la DB à l'infini. `JobStatus.terminal()` (nouvelle méthode canonique sur l'enum) est désormais la seule source ; réutilisée par le stream ET le cancel-helper (dé-duplication d'un set qui avait dérivé). +1 test (cancelled ferme, timeout-gardé). 86✓.

- **2026-09-04 — V2 tranche 2 (batching Qdrant)** : `update_vectors` (sync méta post-hoc) envoyait TOUS les points en une requête → 400 sur un gros document (limite ~32 MB), cassant silencieusement la sync et abortant le backfill. Factorisé le batching par octets de `upsert` (`__batched_by_bytes` + `_to_point_vectors`) et appliqué à `update_vectors` ; `set_payload` chunké par count (`__MAX_PAYLOAD_OPS`=2000). +6 tests batching. Façades consommatrices vertes (21✓).

- **2026-09-04 — V2 tranche 3 (fuite bundles d'import)** : la tâche d'import ne nettoyait que le workspace local — l'objet S3 stagé fuyait (le GC ne balaie que les exports). Suppression best-effort de l'objet stagé sur **succès** (après `mark_done` ; pas de retry arq possible sur un succès, contrairement à un échec). +1 assertion. Reste (`[~]`) : la fuite sur import échoué (retry-sensible) → extension du GC transfert (stamp `expires_at` + `list_expired` incluant IMPORT), slice dédié. 3✓.

- **2026-09-04 — V2 tranche 4 (reaper heartbeat + zombie retry, 2× HAUTE)** : agent `backend` dédié, relu ligne-à-ligne + retesté par moi. (1) `list_stale` outerjoin `worker_heartbeats` — un heartbeat FRAIS **veto** le reap (plus de kill d'un job long mais vivant) ; `worker_id` est PK → pas de dup au join. (2) `retry_jobs=False` (racine du zombie) + gardes défensives : dequeue-skip sur tout `JobStatus.terminal()`, `mark_running` clear `cancel_requested` + no-op sur terminal, `_terminate` garde d'ownership (`get_latest_for_document`) — plus d'écrasement d'état doc par un vieux job reapé. +5 tests. **628 passed**, ruff clean. Sans migration. À valider par `/code-review` avant merge (logique de recovery critique).

- **2026-09-04 — V3 tranche 1 (herméticité tests)** : la suite api unitaire écrivait une vraie ligne `audit_log` par requête mutante dans le Postgres dev (`AuditMiddleware` + `AUDIT_ENABLED` défaut True, `audit.record` non mocké) et fuyait des connexions asyncpg. Fixture autouse conftest étendue à `AUDIT_ENABLED=False` ; `test_audit.py` opte à nouveau via une autouse module (les tests d'enregistrement mockent `record`). 548 passed, warnings 35→3.

- **2026-09-04 — V3 tranche 2 (release tag↔version)** : nouveau job `version-guard` dans `release-images.yml` (compare `${GITHUB_REF_NAME#v}` à `src/docforge/pyproject.toml` ; `images` dépend de `[gate, version-guard]`) — un mistag ne peut plus publier 8 images mensongères + `latest`. Commentaires périmés corrigés (release-images, ci.yml) + ligne release de CLAUDE.md (flux v* unifié). Double-run gate sur tag v* noté pour dédup. YAML validé.

- **2026-09-04 — V3 tranche 3 (deps sécurité docforge)** : `uv lock --upgrade-package` ciblé — pypdf 6.14.2→**6.17.0** (parse les uploads non fiables à l'intake, CVE-2026-82398), aiohttp 3.14.1→3.14.3, h2 4.3.0→4.4.1, setuptools 82.0.1→84.0.0. `uv sync` + suite complète **1348 passed**. (Note : les échecs `test_correlation_runner` vus en isolation passent en suite complète → problème d'isolation/ordre, pas un bug — V8.)

- **2026-09-04 — V3 tranche 4 (deps sécurité mcp)** : lock mcp — cryptography 49.0.0→**50.0.1** (PYSEC-2026-3552), setuptools→84.0.0, et mcp 1.28.0→**1.29.1** en contraignant `mcp>=1.28.1,<2` dans pyproject (un `--upgrade-package mcp` sautait sinon en 2.1.1, cassant l'API FastMCP — pin `<2` défensif). Gate mcp : 42 tests, ruff+mypy clean.

- **2026-09-04 — V4 tranche 1 (crash rerank degrade)** : le chemin de dégradation du rerank renvoyait `score=judged[0].score` (score de FUSION, >1.0 en RRF 3+ branches / DBSF) → `ValidationError` sur `ScoredOutput(le=1)` DANS `run()` → 422 trompeur précisément quand le reranker est down. Clampé à `[0,1]` (`min(1.0, max(0.0, …))`). +1 test (fusion 1.8 → clamp 1.0, pas de crash). 12✓, ruff clean.

- **2026-09-04 — V4 tranche 2 (troncation top_n)** : le nœud rerank ne jugeait que `config.top_n` (défaut 50) puis hydrate cappait à `top_k` → un `limit` 51-100 renvoyait silencieusement ≤50 hits sur une collection rerank-enabled. Le nœud juge désormais `max(top_n, top_k)`. +1 test (top_k>top_n juge tout) + test cap ajusté. Suite search 42✓.

- **2026-09-04 — V4 tranche 3 (paddle coût OCR)** : `CostPlanExtractor.__enrich` utilisait une liste local-free hardcodée `('rapidocr','bge_server')` (sans `paddle`) → une chaîne OCR `[paddle → mistral]` était pricée à $0.00 (paddle vu comme payé, escalade Mistral cachée). Remplacé par le canonique `LOCAL_FREE_KINDS`. +1 test paddle→mistral. 12✓.

## Avancement

| Vague | Total | Fait |
|---|---|---|
| V1 | 30 | 7 (+1 partiel) |
| V2 | 4 | 0 |
| V3 | 1 | 0 |
| V4 | 1 | 0 |
| V5 | 2 | 0 |
| V6 | 0 | 0 |
| V7 | 21 | 0 |
| V8 | 188 | 0 |


## V1 — Sécurité & authz (avant tout déploiement multi-tenant)  (30)

### Backend API

- [x] **🔴 HAUTE** · `security` — Cross-tenant write: PATCH /documents/{id}/enabled and POST /documents/{id}/reingest enforce no collection scope  
  `src/docforge/app/backend/routers/documents/router.py:205` _(aussi: security)_
- [x] **🔴 HAUTE** · `security` — GET /collections returns every tenant's full contract to any READ key (no scope filter)  
  `src/docforge/app/backend/routers/collections/router.py:52` _(aussi: security)_
- [x] **🟠 MOYENNE** · `security` — GET /blobs/{hash} serves uploaded HTML inline on the app/UI origin — stored XSS vector  
  `src/docforge/app/backend/routers/blobs/router.py:45`

### Frontend

- [x] **🔴 HAUTE** · `security` — "View original" opens untrusted uploaded files same-origin via blob: URL — stored XSS can steal the API token  
  `src/docforge/app/frontend/src/api/blobs.ts:23`

### Hygiène logs

- [x] **🔴 HAUTE** · `security` — Startup config dump prints POSTGRES_DSN / REDIS_URL unmasked — DB and Redis passwords land in clear in logs (and Loki)  
  `src/docforge/app/config/runtime_config.py:206`
- [ ] **🟠 MOYENNE** · `security` — Log injection: user-controlled names/filenames logged raw with no sanitization, while the repo sanitizes correlation ids for exactly this reason  
  `src/docforge/app/backend/routers/documents/router.py:201`
- [ ] **⚪ FAIBLE** · `security` — job.error / preflight / health `detail` persist raw provider exception strings — provider-echoed credentials and userinfo-bearing base_urls pass through unredacted  
  `src/docforge/worker/backend/libs/jobs/core.py:291`

### Sécurité & authz

- [x] **🔴 HAUTE** · `security` — .dcexport import lets a bundle overwrite arbitrary S3 objects (attacker-controlled s3_key)  
  `src/docforge/worker/backend/libs/collection_transfer/restore/importer.py:195`
- [x] **🔴 HAUTE** · `security` — MCP HTTP tools read arbitrary files from the MCP container (file_path tool inputs)  
  `src/mcp/libs/tools/documents.py:25`
- [~] **🟠 MOYENNE** · `security` — Collection import bypasses the CREATE capability and skips creator scope-grant  
  `src/docforge/app/backend/routers/transfers/router.py:85` _(aussi: backend-api)_
- [~] **🟠 MOYENNE** · `security` — Import resource exhaustion: decompression bomb + whole-corpus buffering in the worker  
  `src/docforge/worker/backend/libs/collection_transfer/bundle/archive.py:62`
- [x] **🟠 MOYENNE** · `security` — SSRF / internal-network oracle via per-collection provider base_url (unmitigated, unacknowledged)  
  `src/docforge/shared/libs/pipelines/nodes/openai_compat/preflight.py:92`
- [ ] **⚪ FAIBLE** · `bug` — 500-instead-of-4xx and scope-gate edge cases (grouped)  
  `src/docforge/app/backend/routers/auth/whoami.py:40`
- [ ] **⚪ FAIBLE** · `design` — Hardening smells (grouped): blob/HTML response headers, MCP client cache, redaction export list  
  `src/docforge/app/backend/routers/blobs/router.py:45`
- [ ] **⚪ FAIBLE** · `divergence-doc` — Imported pipeline/search blobs are stored without the fail-fast validation every other write path enforces  
  `src/docforge/worker/backend/libs/collection_transfer/restore/importer.py:147`
- [ ] **⚪ FAIBLE** · `security` — Unauthenticated requests bypass the rate limiter; XFF trusted by default  
  `src/docforge/app/backend/app.py:86`

### Dépendances & licences

- [ ] **🟠 MOYENNE** · `security` — GPU images ship torch 2.6.0 (cu124 index is EOL) while CPU ships 2.12.1/2.13.0; CPU worker torch also below the PYSEC-2025-194 fix  
  `src/docforge/uv.lock:4661`
- [x] **🟠 MOYENNE** · `security` — Stale transitive pins with published security fixes across the docforge and mcp locks  
  `src/docforge/uv.lock:99`
- [x] **🟠 MOYENNE** · `security` — pypdf 6.14.2 carries 6 known advisories and parses untrusted uploads at intake  
  `src/docforge/uv.lock:3528`
- [x] **⚪ FAIBLE** · `security` — mcp 1.28.0 in the MCP server lock has a known advisory fixed one patch away (1.28.1)  
  `src/mcp/uv.lock:514`
- [ ] **⚪ FAIBLE** · `security` — transformers<5 pins freeze both ML services on a line whose security fixes are 5.x-only  
  `src/docforge/pyproject.toml:95`

### Infra & compose

- [x] **🟠 MOYENNE** · `consistency` — Fresh-clone credential mismatch: base.yml's default POSTGRES_DSN (docforge:docforge) does not match the shipped postgres.env.example (change_me)  
  `compose/base.yml:43`
- [x] **🟠 MOYENNE** · `security` — Unauthenticated Gotenberg published on host port 10045 in every scenario including prod, contradicting docs/configuration.md's exposure claim  
  `compose/base.yml:272`

### Infra .claude

- [ ] **🟠 MOYENNE** · `security` — hook logs retain secrets in plaintext with unbounded retention (full tool_input/tool_response of every call)  
  `.claude/hooks/hooks.py:117`
- [ ] **⚪ FAIBLE** · `security` — settings.json runs every session in bypassPermissions with a blanket allow list  
  `.claude/settings.json:9`

### Serveurs modèles

- [x] **🟠 MOYENNE** · `security` — paddle_server buffers unbounded request bodies — no size cap on /ocr or /layout-parsing  
  `src/paddle_server/backend/routers/ocr/router.py:40`

### CI & release

- [ ] **⚪ FAIBLE** · `security` — Workflow hardening gaps: no permissions on ci/gate, gate inherits packages:write during releases, mutable action refs in the OIDC publish job  
  `.github/workflows/ci.yml:20`

### Middlewares HTTP

- [ ] **⚪ FAIBLE** · `security` — X-Forwarded-For trusted by default (leftmost hop) while the default deployment has no proxy — forgeable audit client_ip out-of-box, rate-limit keying bypass when enabled with auth off  
  `src/docforge/app/config/runtime_config.py:112`

### Search & retrieval

- [x] **⚪ FAIBLE** · `security` — Search-side SSRF parity: per-collection base_urls + probe endpoints form an internal-network reachability oracle  
  `src/docforge/app/backend/routers/search/helpers.py:339`

### Télémétrie

- [ ] **⚪ FAIBLE** · `security` — Grouped low-severity security notes on the telemetry overlay  
  `compose/overlays/telemetry.yml:84`


## V2 — Fiabilité: jobs, stores, transferts  (4)

### Données Postgres·Qdrant·S3

- [~] **🔴 HAUTE** · `bug` — Import staging bundles leak in S3 forever — GC sweeps exports only  
  `src/docforge/shared/libs/services/db/postgresql/apis/transfer_api.py:47`
- [x] **🔴 HAUTE** · `bug` — QdrantIndexApi.update_vectors sends all points in one request — breaks meta-vector sync for large documents  
  `src/docforge/shared/libs/services/db/qdrant/apis/index_api.py:93`

### Worker & jobs

- [x] **🔴 HAUTE** · `bug` — Reaper can kill live long-running jobs: staleness keyed only on job.updated_at, worker heartbeat never consulted  
  `src/docforge/shared/libs/services/db/postgresql/apis/job_api.py:570`
- [x] **🔴 HAUTE** · `bug` — Zombie arq retry of a reaped job spuriously cancels it and can clobber the document's terminal state  
  `src/docforge/shared/libs/services/db/postgresql/apis/job_api.py:74`


## V3 — Release, CI, dépendances  (1)

### CI & release

- [x] **🔴 HAUTE** · `bug` — release-images has no tag-vs-version guard — a mistag publishes images at a wrong version and breaks lockstep  
  `.github/workflows/release-images.yml:72`


## V4 — Search & coûts  (1)

### Search & retrieval

- [x] **🔴 HAUTE** · `bug` — Rerank degrade path crashes on fusion scores > 1.0 (ScoredOutput le=1), defeating the degradation it exists for  
  `src/docforge/shared/libs/pipelines/search/nodes/rerank/cross_encoder/core.py:126`


## V5 — Moteur & pipeline  (2)

### IR & modèles

- [ ] **🔴 HAUTE** · `design` — BlobNormalizer heal silently discards graph-level customisations from the documented /edit surface  
  `src/docforge/shared/libs/pipelines/ingest/stages/normalizer.py:104`

### Pipeline ingest

- [ ] **🔴 HAUTE** · `bug` — Preflight coverage gaps: figure_classify (VLM), semantic chunker, metagen default endpoint — with a config comment falsely claiming preflight coverage  
  `src/docforge/shared/libs/pipelines/ingest/nodes/enrich/figure_classify/core.py:56`


## V7 — Documentation  (21)

### Documentation

- [ ] **🔴 HAUTE** · `divergence-doc` — metadata-architecture.md is a legacy-engine reference presented as current — schema, stages and hashes all wrong  
  `docs/metadata-architecture.md:1`
- [ ] **🔴 HAUTE** · `divergence-doc` — rest-api.md documents removed ColBERT params use_late_interaction / rescore_pool_size that now 422  
  `docs/rest-api.md:478` _(aussi: claude-infra, docs-freshness, search-runtime)_
- [ ] **🟠 MOYENNE** · `divergence-doc` — PIPELINE.md (the self-declared living reference) omits the deliver family / bundle terminal entirely  
  `src/docforge/PIPELINE.md:61`
- [ ] **🟠 MOYENNE** · `divergence-doc` — configuration.md misses the whole idempotency + audit env-var families  
  `docs/configuration.md:24`
- [ ] **🟠 MOYENNE** · `divergence-doc` — configuration.md: BGE_M3_MAX_LENGTH default wrong (doc 8192, code 2048); several bge/paddle vars undocumented  
  `docs/configuration.md:181`
- [ ] **🟠 MOYENNE** · `divergence-doc` — configuration.md: FASTAPI_APP_VERSION described as required with default 0.2.0 — actually optional, defaults from DOCFORGE_TAG  
  `docs/configuration.md:41`
- [ ] **🟠 MOYENNE** · `divergence-doc` — mcp.md tool catalogue misses list_audit; tool totals stale (54 and 38 vs actual 55)  
  `docs/mcp.md:168` _(aussi: sdk-mcp)_
- [ ] **🟠 MOYENNE** · `divergence-doc` — python-sdk.md: jobs.list() return type wrong — returns JobPage, not list[JobStatus]  
  `docs/python-sdk.md:338`
- [ ] **🟠 MOYENNE** · `divergence-doc` — rest-api.md filters contract under-documented: range predicates (gte/gt/lte/lt) exist but are absent  
  `docs/rest-api.md:476`
- [ ] **🟠 MOYENNE** · `divergence-doc` — rest-api.md misses 8 live endpoints: collection health/storage/reingest, job cancel, and all 4 transfers routes  
  `docs/rest-api.md:41`
- [ ] **⚪ FAIBLE** · `divergence-doc` — CONTRIBUTING.md: 'monorepo of four standalone uv projects' — paddle_server is a fifth, CI-gated package  
  `CONTRIBUTING.md:3`
- [ ] **⚪ FAIBLE** · `divergence-doc` — Ground-truth docs stale: CLAUDE.md family/node lists miss structgen+deliver; tests list incomplete; rules/architecture.md says preflight 'reste à ajouter' though shipped  
  `CLAUDE.md:1`
- [ ] **⚪ FAIBLE** · `divergence-doc` — PIPELINE.md stale statuses: block-id remap marked pending though shipped; item-index-in-progress-events caveat outdated; tree misses vlm_entry/parser kinds; nodes list misses structgen  
  `src/docforge/PIPELINE.md:485`
- [ ] **⚪ FAIBLE** · `divergence-doc` — README.md workflows note omits release-images.yml  
  `README.md:169`
- [ ] **⚪ FAIBLE** · `divergence-doc` — Response payloads richer than documented: SearchHit, JobStatus and jobs list pagination under-described in rest-api.md  
  `docs/rest-api.md:493`
- [ ] **⚪ FAIBLE** · `divergence-doc` — architecture.md grouped staleness: SDK resource list, frontend gate steps, self-referential rename note  
  `docs/architecture.md:75`
- [ ] **⚪ FAIBLE** · `divergence-doc` — brand.md muted/pending hex #8a8378 diverges from the implemented tokens  
  `docs/brand.md:28`
- [ ] **⚪ FAIBLE** · `divergence-doc` — deployment-resources.md still flags getting-started.md's '~10 GB / 8 GB' claim as needing a fix that already landed  
  `docs/deployment-resources.md:39`
- [ ] **⚪ FAIBLE** · `consistency` — getting-started.md port-range claims inconsistent: '10040–10048' vs published 10049 and troubleshooting's 10040–10052  
  `docs/getting-started.md:19`
- [ ] **⚪ FAIBLE** · `divergence-doc` — getting-started.md: field-type list names 6 of 11 types  
  `docs/getting-started.md:182`
- [ ] **⚪ FAIBLE** · `consistency` — python-sdk.md auth section drops the CREATE capability from the KeyPermissions bullet  
  `docs/python-sdk.md:387`


## V8 — Outillage: .claude, tests, infra, télémétrie  (188)

### Backend API

- [x] **🔴 HAUTE** · `bug` — SSE job stream never closes for a CANCELLED job — polls the DB forever  
  `src/docforge/app/backend/routers/jobs/stream.py:19`
- [ ] **🟠 MOYENNE** · `bug` — Check-then-insert races surface as 500: duplicate concurrent upload and duplicate collection name hit unique constraints uncaught  
  `src/docforge/app/backend/routers/documents/router.py:125`
- [ ] **🟠 MOYENNE** · `perf` — Unbounded whole-collection reads: estimate default scope, explorer document list, and bulk delete have no cap  
  `src/docforge/app/backend/libs/estimate/service.py:130` _(aussi: money-math)_
- [ ] **🟠 MOYENNE** · `design` — update_collection applies contract, schema, blob and override writes as separate commits — a mid-sequence failure leaves a half-applied PATCH  
  `src/docforge/app/backend/routers/collections/router.py:348`
- [ ] **⚪ FAIBLE** · `bug` — GET /auth/whoami 500s on a malformed permissions blob instead of degrading like the authz gate  
  `src/docforge/app/backend/routers/auth/whoami.py:40`
- [ ] **⚪ FAIBLE** · `consistency` — Grouped minor issues: unbounded bulk-chunk patch, transfer info disclosed before scope check, catch-all ValueError→422, READ-triggered export side effects, whole-blob buffering, duplicated lifespan step number  
  `src/docforge/app/backend/routers/explorer/models.py:134`
- [ ] **⚪ FAIBLE** · `divergence-doc` — RUNTIME_CONFIG idempotency comment claims key create/rotate are eligible endpoints — eligibility.py deliberately excludes them  
  `src/docforge/app/config/runtime_config.py:118`

### Infra & compose

- [ ] **🔴 HAUTE** · `bug` — proxy.yml Caddyfile bind mount resolves outside the repo — TLS add-on broken in every documented invocation  
  `compose/overlays/proxy.yml:48` _(aussi: telemetry-configs)_
- [ ] **🟠 MOYENNE** · `design` — Dev builds retag the GHCR prod image names — a later prod `up` on the same host silently runs the dev-built image  
  `compose/overlays/dev.yml:30`
- [ ] **🟠 MOYENNE** · `consistency` — Grafana admin password mechanism drift: Makefile exports a variable nothing consumes; root .env.example documents the retired mechanism  
  `Makefile:83`
- [ ] **🟠 MOYENNE** · `perf` — No .dockerignore for the src/docforge build context — 386 MB .venv, host node_modules stub and dist enter every app/worker build  
  `src/.dockerignore:1`
- [ ] **🟠 MOYENNE** · `divergence-doc` — compose/README.md documents a nonexistent compose/telemetry/ dir and the wrong overlay path rule  
  `compose/README.md:17` _(aussi: telemetry-configs)_
- [ ] **🟠 MOYENNE** · `divergence-doc` — dev.yml/gpu.yml headers document a manual -f invocation whose paths resolve outside the repo, plus a 'last-include wins' claim that contradicts the verified first-wins rule  
  `compose/overlays/dev.yml:4`
- [ ] **🟠 MOYENNE** · `design` — docforge_app has no healthcheck — the one service everything else fronts can wedge silently  
  `compose/base.yml:23`
- [ ] **⚪ FAIBLE** · `design` — Robustness gaps: missing healthchecks/limits on secondary services, app's incomplete depends_on, S3 gateway not probed (grouped)  
  `compose/overlays/telemetry.yml:74`
- [ ] **⚪ FAIBLE** · `divergence-doc` — Stale comments across compose/CI/Dockerfiles (grouped)  
  `compose/base.yml:15`

### Infra .claude

- [ ] **🔴 HAUTE** · `design` — .claude/ is gitignored and untracked — the entire agent infrastructure (750KB of memory, 10 agents, rules, hooks) exists in a single unversioned copy that was already silently lost once  
  `.gitignore:58`
- [ ] **🔴 HAUTE** · `bug` — /dev, /test and /phase-status skills are hard-broken: nonexistent compose files, dirs and service names  
  `.claude/commands/dev.md:25`
- [ ] **🔴 HAUTE** · `divergence-doc` — All 10 agent definitions target the ghost tree src/docforge-rework/ and call the live tree 'frozen legacy'  
  `.claude/agents/pipeline.md:29`
- [ ] **🔴 HAUTE** · `bug` — hooks.py log rotation never deletes: docstring promises 'only one rotated copy', code keeps all — 199MB and growing unbounded  
  `.claude/hooks/hooks.py:88`
- [ ] **🟠 MOYENNE** · `divergence-doc` — Agent-memory rot: 26 files still teach rework-era paths, and 4+ memories document the ColBERT feature that no longer exists  
  `.claude/agent-memory/backend/colbert-named-vector.md:1`
- [ ] **🟠 MOYENNE** · `divergence-doc` — The 3 rpi skill commands still describe the deleted S0→S6 static engine (engine.py DAG, provider Protocols, S2_ENRICH_ENABLED, phase table)  
  `.claude/commands/rpi/research.md:22`
- [ ] **🟠 MOYENNE** · `dead-code` — The knowledge graph orchestrator.md builds its whole long-term-memory protocol on does not exist — wrong path in the doc, and no file at the configured path either  
  `.claude/rules/orchestrator.md:100`
- [ ] **🟠 MOYENNE** · `divergence-doc` — architecture.md claims per-node preflight() 'reste à ajouter' — it shipped, is on by default, and is CLAUDE.md invariant 4  
  `.claude/rules/architecture.md:76`
- [ ] **🟠 MOYENNE** · `consistency` — orchestrator.md contradicts itself and the tree: auto-improvement table routes pipeline updates to src/docforge-rework/PIPELINE.md  
  `.claude/rules/orchestrator.md:76`
- [ ] **⚪ FAIBLE** · `consistency` — Grouped low-severity smells across .claude/: decorative paths filter, deprecated utcnow, stale lock/pycache, misnamed memory file  
  `.claude/rules/brand.md:3`
- [ ] **⚪ FAIBLE** · `dead-code` — scripts/update_imports.py is a dead one-off targeting the deleted legacy layout, still tracked with no caller  
  `scripts/update_imports.py:15`

### SDK & MCP

- [ ] **🔴 HAUTE** · `test-gap` — OpenAPI parity guards silently pass on additive drift — no completeness check over schemas or routes  
  `src/docforge_sdk/tests/check_schema_drift.py:89`
- [ ] **🟠 MOYENNE** · `test-gap` — Async/sync lockstep guard and unit tests skip the three newest SDK resources (audit, corpus, snippets)  
  `src/docforge_sdk/tests/unit/test_resource_parity.py:25`
- [ ] **🟠 MOYENNE** · `divergence-doc` — MCP tool surface is not the promised 'full REST surface': collection health probe and collection-level bulk reingest have no tool  
  `src/mcp/libs/tools/collections.py:24`
- [ ] **🟠 MOYENNE** · `design` — MCP tools swallow the API error body — a 4xx surfaces to the LLM as an opaque status code  
  `src/mcp/libs/tools/search.py:50`
- [ ] **🟠 MOYENNE** · `divergence-doc` — docs/python-sdk.md is four resources behind the SDK (transfers, corpus, snippets, audit all undocumented)  
  `docs/python-sdk.md:108` _(aussi: docs-freshness)_
- [ ] **⚪ FAIBLE** · `consistency` — Minor SDK/MCP inconsistencies (grouped): client docstrings omit corpus, divergent get_pipeline_design default, stale 0.1.1 dist artifacts  
  `src/docforge_sdk/docforge_sdk/client.py:31`
- [ ] **⚪ FAIBLE** · `design` — ScopedSdkProvider eviction is FIFO-not-LRU and closes evicted clients via an unreferenced fire-and-forget task  
  `src/mcp/libs/scoped_sdk.py:127`

### Serveurs modèles

- [ ] **🔴 HAUTE** · `bug` — bge keep-warm task bypasses the engine locks and races real forward passes on the same model instances  
  `src/bge_server/backend/lifespan.py:49`
- [ ] **🟠 MOYENNE** · `design` — /embed_all has no back-pressure: bypasses the bounded queues, can never return 503  
  `src/bge_server/libs/batching/engine.py:385`
- [ ] **🟠 MOYENNE** · `design` — Bad image bytes on /ocr surface as HTTP 500 with raw exception text — client errors indistinguishable from server faults  
  `src/paddle_server/backend/routers/ocr/router.py:47`
- [ ] **🟠 MOYENNE** · `dead-code` — PADDLE_USE_DOC_UNWARPING env var is dead — its comment promises operators an override that silently does nothing  
  `src/paddle_server/config_loader.py:94`
- [ ] **🟠 MOYENNE** · `consistency` — Thread-budget derivation assumes 1 concurrent model call while the two-lock engine allows 2 — engine docstring and service code contradict each other  
  `src/bge_server/libs/bge_models/service.py:87`
- [ ] **🟠 MOYENNE** · `divergence-doc` — no-AVX SIGILL constraint is documented in docs/ but completely unguarded in paddle_server — container reports healthy, then dies on first inference  
  `src/paddle_server/backend/routers/health/router.py:46`
- [ ] **⚪ FAIBLE** · `consistency` — /rerank claims to mirror TEI but returns input order where TEI returns score-descending order  
  `src/bge_server/backend/routers/inference/router.py:220`
- [ ] **⚪ FAIBLE** · `consistency` — bge_server stale doc/comment cluster: retired single-lock design, wrong worker count, phantom constructor args, dead port reference  
  `src/bge_server/libs/batching/worker.py:31`
- [ ] **⚪ FAIBLE** · `dead-code` — paddle_server PADDLE_PIN_INFO is exported but never used — its docstring claims it feeds /health and the engine block  
  `src/paddle_server/libs/ppstructure/revision.py:14`

### Tests

- [x] **🔴 HAUTE** · `bug` — Unit suite silently writes real rows into the live dev Postgres (audit middleware unmocked)  
  `src/docforge/tests/units/api/conftest.py:41`
- [ ] **🟠 MOYENNE** · `divergence-doc` — CLAUDE.md documents `uv run mypy .` but mypy is neither installed nor runnable on this tree  
  `CLAUDE.md:48`
- [ ] **🟠 MOYENNE** · `test-gap` — ForEach max_concurrency is asserted as config plumbing but never as runtime behavior  
  `src/docforge/tests/units/stages/test_figure_concurrency.py:26`
- [ ] **🟠 MOYENNE** · `test-gap` — No sweep test that every /api/v1 route carries an authz capability dependency  
  `src/docforge/tests/units/api/test_authz_scoping.py:1`
- [ ] **🟠 MOYENNE** · `test-gap` — Token introspection (GET /auth/whoami, v0.13.0) has zero tests  
  `src/docforge/app/backend/routers/auth/whoami.py:21`
- [ ] **🟠 MOYENNE** · `test-gap` — Transition-priority chain only pinned for ScoreBelow>WhenEquals; the rest of the documented order is untested  
  `src/docforge/tests/units/engine/test_conditions.py:112`
- [ ] **⚪ FAIBLE** · `test-gap` — Grouped low-severity assertion smells: a vacuous mock assert, SQL-substring predicates, and unmapped SDK 5xx/transport errors  
  `src/docforge/tests/units/api/test_auth.py:127`
- [ ] **⚪ FAIBLE** · `test-gap` — Idempotency middleware: the cache-a-4xx-and-replay-it branch is completely unpinned  
  `src/docforge/tests/units/api/test_idempotency.py:357`
- [ ] **⚪ FAIBLE** · `design` — pytest.ini smells: blanket DeprecationWarning ignore, unguarded tests/db in default collection, unfiltered warning noise  
  `src/docforge/pytest.ini:9`

### API pipelines

- [ ] **🟠 MOYENNE** · `design` — Palette scoping (FAMILY_KINDS / FAMILIES / SELECTABLE) is advisory only — /edit accepts any registered kind and the write-time guard is pipeline-agnostic  
  `src/docforge/shared/libs/pipelines/edit/editor.py:74`
- [ ] **⚪ FAIBLE** · `divergence-doc` — CLAUDE.md families list is stale vs the registered palette  
  `CLAUDE.md:106`
- [ ] **⚪ FAIBLE** · `consistency` — Grouped low-severity smells across the discovery/edit surface  
  `src/docforge/shared/libs/pipelines/registry.py:218`
- [ ] **⚪ FAIBLE** · `dead-code` — PipelineCatalog.palette() is dead code (and would leak cross-pipeline kinds if used)  
  `src/docforge/shared/libs/pipelines/introspection/catalog.py:95`

### CI & release

- [x] **🟠 MOYENNE** · `divergence-doc` — CLAUDE.md release instructions contradict the workflows: 'Le SDK reste sur les tags sdk-v*' but release-sdk now fires on v* too  
  `CLAUDE.md:44` _(aussi: deps-licenses)_
- [ ] **🟠 MOYENNE** · `perf` — Every v* tag runs the full monorepo gate twice in parallel (release-images + release-sdk each call gate.yml)  
  `.github/workflows/release-sdk.yml:39`
- [ ] **⚪ FAIBLE** · `consistency` — Comment/doc drift bundle: 'fully serviceless' gate runs a Postgres service container; docs/architecture.md and the release-images header describe an older gate/publish matrix  
  `.github/workflows/gate.yml:11`
- [ ] **⚪ FAIBLE** · `perf` — Every push to a PR branch runs the gate twice (push event + pull_request event, distinct concurrency groups)  
  `.github/workflows/ci.yml:12`
- [ ] **⚪ FAIBLE** · `test-gap` — Lockstep version test and set_version.sh cover only 3 of 6 version declarations — frontend package.json, bge_server, paddle_server are outside the loop  
  `src/docforge/tests/units/test_version_alignment.py:30`
- [ ] **⚪ FAIBLE** · `design` — Partial-release window: fail-fast:false image matrix + independent SDK publish can leave GHCR half-published with :latest moved  
  `.github/workflows/release-images.yml:51`

### Coûts & estimation

- [ ] **🟠 MOYENNE** · `test-gap` — No unit tests for the override merger, the override contract, or the sampling-cap seam  
  `src/docforge/app/backend/libs/estimate/merger.py:28`
- [x] **🟠 MOYENNE** · `bug` — OCR plan extractor's local-kind list omits 'paddle' — paddle-headed chain hides a paid Mistral escalation  
  `src/docforge/shared/libs/pipelines/ingest/estimate/plan.py:94`
- [ ] **🟠 MOYENNE** · `design` — Per-figure paid OCR volume is modeled by scanned_page_ratio (default 0), not figure count — default estimate prices a paid per-figure OCR pipeline at $0.00 with cost_complete=True  
  `src/docforge/shared/libs/pipelines/ingest/estimate/estimator.py:201`
- [ ] **🟠 MOYENNE** · `divergence-doc` — Post-hoc $ meter counts only LLM/VLM/structgen — paid embed and paid OCR spend is never metered, while the estimate prices both  
  `src/docforge/worker/backend/libs/jobs/usage.py:51`
- [ ] **⚪ FAIBLE** · `design` — Meter undercounts on retries/failed paid attempts, and search-time LLM spend is metered nowhere  
  `src/docforge/shared/libs/pipelines/nodes/openai_compat/client.py:52`
- [ ] **⚪ FAIBLE** · `bug` — Override validation gaps: negative embed/OCR rates and infinite assumption values are accepted  
  `src/docforge/app/backend/libs/estimate/overrides.py:32`
- [ ] **⚪ FAIBLE** · `consistency` — Per-collection rate overrides shape the estimate but never the meter — contradicting the 'priced from identical numbers' contract  
  `src/docforge/shared/libs/pipelines/ingest/estimate/rates.py:6`
- [ ] **⚪ FAIBLE** · `consistency` — Pricing table is accurate but a generation behind (cutoff: Jan 2026)  
  `src/docforge/shared/libs/pipelines/nodes/openai_compat/pricing.py:13`
- [ ] **⚪ FAIBLE** · `design` — Sampler/estimator representativeness smells (grouped lows)  
  `src/docforge/app/backend/libs/estimate/sampler.py:85`
- [ ] **⚪ FAIBLE** · `dead-code` — chunk_overlap_ratio override is dead and the merger's chunker-wins fallback is asymmetric vs its own docstrings  
  `src/docforge/app/backend/libs/estimate/merger.py:85`

### Données Postgres·Qdrant·S3

- [ ] **🟠 MOYENNE** · `bug` — Bulk chunk toggle spanning collections is not atomic across the two stores  
  `src/docforge/shared/libs/services/db/facades/enablement_facade.py:117`
- [ ] **🟠 MOYENNE** · `perf` — Disabled-document exclusion list is unbounded and rides every prefetch branch of every search  
  `src/docforge/shared/libs/services/db/facades/search_facade.py:86`
- [ ] **🟠 MOYENNE** · `bug` — Orphan-blob purge races a concurrent ingest sharing the same content hash  
  `src/docforge/shared/libs/services/db/postgresql/apis/blob_api.py:221`
- [ ] **⚪ FAIBLE** · `divergence-doc` — CLAUDE.md structure tree names a `migrations/` root that does not exist  
  `CLAUDE.md:115`
- [ ] **⚪ FAIBLE** · `dead-code` — Dead data-layer code: ArtifactCacheFacade.drop_for_document and ArtifactCacheApi.referenced_hashes have no production caller  
  `src/docforge/shared/libs/services/db/facades/artifact_cache_facade.py:137`
- [ ] **⚪ FAIBLE** · `consistency` — Grouped low-severity naming inconsistencies in tables/indexes/constraints  
  `src/docforge/shared/libs/services/db/postgresql/tables/observability/worker_heartbeat.py:20`
- [ ] **⚪ FAIBLE** · `consistency` — Grouped minor smells: stale docstrings, unbatched/sequential store calls, unbounded legacy listing, protected-member coupling  
  `src/docforge/shared/libs/services/db/facades/meta_vector_sync_facade.py:104`
- [ ] **⚪ FAIBLE** · `design` — Migration-only functional/GIN indexes are invisible to autogenerate and at risk of a proposed DROP  
  `src/docforge/shared/libs/services/db/postgresql/tables/documents/document_metadata.py:30`
- [ ] **⚪ FAIBLE** · `bug` — Retry does not clear the structured failure breadcrumb — DONE jobs keep failed_node_id from a prior attempt  
  `src/docforge/shared/libs/services/db/postgresql/apis/job_api.py:74`
- [ ] **⚪ FAIBLE** · `bug` — config_version has no unique (collection_id, version) — concurrent config updates mint duplicate versions  
  `src/docforge/shared/libs/services/db/facades/collections_facade.py:265`

### Dépendances & licences

- [ ] **🟠 MOYENNE** · `design` — Dependabot has no coverage for the ~14 container images pinned in compose files  
  `.github/dependabot.yml:85`
- [ ] **⚪ FAIBLE** · `consistency` — Licensing/version metadata nits: no license field in 4 pyprojects, no LICENSE in images, off-lockstep service versions, stale MinerU/Marker doc line  
  `src/docforge/pyproject.toml:6`

### Export/import

- [ ] **🟠 MOYENNE** · `design` — Export is not snapshot-consistent: blob hashes and points are read from the live DB after the document pass, so a concurrent reingest/delete produces a bundle that fails at import or silently loses data  
  `src/docforge/worker/backend/libs/collection_transfer/export/exporter.py:225`
- [ ] **🟠 MOYENNE** · `bug` — Hard worker kill mid-import leaves a permanent half-imported collection and a forever-RUNNING transfer row — no reaper covers collection_transfer  
  `src/docforge/worker/backend/libs/jobs/transfer.py:136`
- [ ] **🟠 MOYENNE** · `perf` — Import buffers every blob's bytes in memory at once — up to IMPORT_MAX_BUNDLE_BYTES (5 GiB default) resident — while export streams one blob at a time  
  `src/docforge/worker/backend/libs/collection_transfer/restore/importer.py:187`
- [ ] **⚪ FAIBLE** · `consistency` — Dangling-reference handling is inconsistent: primary FKs fail loudly (KeyError) but parent/caption links, unknown metadata fields, and stale point payload document_id degrade silently  
  `src/docforge/worker/backend/libs/collection_transfer/restore/rows.py:132`
- [ ] **⚪ FAIBLE** · `divergence-doc` — Five code comments still claim ids are 'preserved verbatim'/'id-preserving' while the import regenerates every id — the export-side summary directly contradicts the restore-side design  
  `src/docforge/worker/backend/libs/collection_transfer/export/rows.py:4`
- [ ] **⚪ FAIBLE** · `bug` — Import success and counts are taken from the manifest, never reconciled against what was actually restored; a data file absent from manifest.files imports silently as empty  
  `src/docforge/worker/backend/libs/collection_transfer/restore/importer.py:123`
- [ ] **⚪ FAIBLE** · `test-gap` — Remap test coverage is happy-path only: 1 doc/1 chunk/1 block, no parent chains, no corrupt-bundle, no zero-point, no double-import cases  
  `src/docforge/tests/units/transfer/test_import.py:24`
- [ ] **⚪ FAIBLE** · `consistency` — config_versions history is exported into collection.json (redacted) but silently discarded on import — the new collection gets only a fresh v1 'creation' snapshot  
  `src/docforge/worker/backend/libs/collection_transfer/restore/importer.py:139`

### Frontend

- [ ] **🟠 MOYENNE** · `bug` — A chunks-fetch error blanks the entire Layout tab, contradicting its own degrade-without-chunks design  
  `src/docforge/app/frontend/src/features/explorer/DocumentPage.tsx:133` _(aussi: new-batch)_
- [ ] **🟠 MOYENNE** · `divergence-doc` — Brand rule "Nothing below 11px" violated: hardcoded fontSize 9 in the new Layout components  
  `src/docforge/app/frontend/src/features/explorer/layout/ChunkProvenance.tsx:55` _(aussi: new-batch)_
- [ ] **🟠 MOYENNE** · `bug` — Job-detail ETA never subtracts completed stages (job-status set tested against event statuses)  
  `src/docforge/app/frontend/src/features/monitoring/state/useJobDetail.ts:191`
- [ ] **🟠 MOYENNE** · `perf` — Layout tab loads and renders the whole document eagerly — N simultaneous page-image fetches, refetched on every tab switch, plus unmemoized per-render recomputation  
  `src/docforge/app/frontend/src/features/explorer/layout/LayoutTab.tsx:91` _(aussi: new-batch)_
- [ ] **🟠 MOYENNE** · `test-gap` — No tests anywhere in the batch: pure grouping/segmentation helpers, LayoutTab smoke, /provenance endpoint, startup reclaim and the CancelledError terminal path are all untested  
  `src/docforge/app/frontend/src/features/explorer/layout/chunkGrouping.ts:47` _(aussi: frontend, tests-audit)_
- [ ] **🟠 MOYENNE** · `bug` — Per-document tab caches never reset when documentId changes without a remount — wrong document's data shown  
  `src/docforge/app/frontend/src/features/explorer/state/useDocumentTabs.ts:59`
- [ ] **🟠 MOYENNE** · `bug` — Provenance returns the latest job even when it failed, so it can describe a run that did NOT produce the displayed IR  
  `src/docforge/shared/libs/services/db/postgresql/apis/job_api.py:67` _(aussi: backend-api)_
- [ ] **🟠 MOYENNE** · `perf` — Search Lab fetches the entire unpaginated document list just to learn "has documents"  
  `src/docforge/app/frontend/src/features/search/SearchLabPage.tsx:48`
- [ ] **🟠 MOYENNE** · `design` — Search Lab filter builder cannot express the documented any-of and range filter forms  
  `src/docforge/app/frontend/src/features/search/SearchFilterBuilder.tsx:115`
- [ ] **🟠 MOYENNE** · `bug` — Stage-rail initial load: unhandled rejection + eternal loading state on discovery failure  
  `src/docforge/app/frontend/src/features/stage-rail/state/useStageRailPage.ts:52`
- [ ] **🟠 MOYENNE** · `bug` — WorkersPanel and JobsPage stop polling permanently after one failed fetch  
  `src/docforge/app/frontend/src/features/monitoring/WorkersPanel.tsx:32`
- [ ] **⚪ FAIBLE** · `design` — CancelledError terminal writes: a second cancellation mid-shield skips the job write, and Exception doesn't catch it  
  `src/docforge/worker/backend/libs/jobs/core.py:258`
- [ ] **⚪ FAIBLE** · `dead-code` — Committed one-off Playwright scripts and QA screenshot binaries under frontend scripts/  
  `src/docforge/app/frontend/scripts/a11y-check.mjs:1` _(aussi: new-batch)_
- [ ] **⚪ FAIBLE** · `design` — File-size and structure rule signals in the new code  
  `src/docforge/app/frontend/src/features/explorer/layout/IrChunkGraph.tsx:1`
- [ ] **⚪ FAIBLE** · `consistency` — Grouped low-severity smells: stale comments, per-render column rebuild, filtered-mode delete accounting, token violations, asymmetric editor hygiene  
  `src/docforge/app/frontend/src/features/corpus/CorpusPage.tsx:64`
- [ ] **⚪ FAIBLE** · `bug` — Layout parse-chain contaminated: "mistral" in the PARSERS set matches the OCR and LLM node kinds  
  `src/docforge/app/frontend/src/features/explorer/layout/LayoutTab.tsx:66`
- [ ] **⚪ FAIBLE** · `consistency` — Low-severity smells in the Layout batch (grouped): hardcoded rgba shadow, bypassed displayPage, unreachable-degenerate unionBbox, dropped empty pages, page-load action error nukes the document page, >200-line files  
  `src/docforge/app/frontend/src/components/PageBoxOverlay.tsx:171`
- [ ] **⚪ FAIBLE** · `bug` — PageScrubber binds its scroll container once and never rebinds; touch drag not handled  
  `src/docforge/app/frontend/src/features/explorer/layout/PageScrubber.tsx:52`
- [ ] **⚪ FAIBLE** · `perf` — PageScrubber scroll handler does O(pages) DOM reads on every scroll event  
  `src/docforge/app/frontend/src/features/explorer/layout/PageScrubber.tsx:56`
- [ ] **⚪ FAIBLE** · `design` — Parser-chain rendering conflates skipped/running with failed, and the parser-kind list is a hand-maintained hardcode  
  `src/docforge/app/frontend/src/features/explorer/layout/LayoutTab.tsx:66`
- [ ] **⚪ FAIBLE** · `design` — Responsive collapse: fixed 476px reserved for the chunk column + connector with no horizontal scroll fallback  
  `src/docforge/app/frontend/src/features/explorer/layout/IrChunkGraph.tsx:197`
- [ ] **⚪ FAIBLE** · `divergence-doc` — SchemaField header comment promises secret masking that the code does not implement  
  `src/docforge/app/frontend/src/components/schema-form/SchemaField.tsx:3`
- [ ] **⚪ FAIBLE** · `consistency` — SearchQueryCard duplicates backend config defaults as display literals  
  `src/docforge/app/frontend/src/features/search-pipeline/SearchQueryCard.tsx:16`
- [ ] **⚪ FAIBLE** · `consistency` — Stale/contradictory comments across the batch: phantom "lane" palette, wrong palette description, outdated tab counts, and a bbox description that contradicts the wire format  
  `src/docforge/app/frontend/src/features/explorer/layout/PageGroupRow.tsx:5`
- [ ] **⚪ FAIBLE** · `divergence-doc` — Startup job reclaim keys on the container hostname, which changes on every container recreate — the crash/hard-kill cases it claims to cover never match  
  `src/docforge/shared/libs/services/db/facades/jobs_facade.py:344`
- [ ] **⚪ FAIBLE** · `bug` — Union-find in buildPageGroups: only the leading page is unioned, and find() infinite-loops on an unseeded key  
  `src/docforge/app/frontend/src/features/explorer/layout/chunkGrouping.ts:50`

### IR & modèles

- [ ] **🟠 MOYENNE** · `divergence-doc` — Chunk table docstring promises deterministic UUID v5 point ids; translator mints random uuid4 per run  
  `src/docforge/shared/libs/services/db/postgresql/tables/chunks/chunk.py:28` _(aussi: db-layer)_
- [ ] **🟠 MOYENNE** · `dead-code` — Dead IR/DB fields surfaced to the API as meaningful data, and an enrichment-trace promise never fulfilled  
  `src/docforge/app/backend/routers/explorer/models_ir.py:25`
- [ ] **🟠 MOYENNE** · `test-gap` — ENGINE_BLOB_VERSION bump is purely manual and already missed once; golden-blob test does not force it  
  `src/docforge/shared/libs/pipelines/ingest/stages/normalizer.py:36`
- [ ] **🟠 MOYENNE** · `bug` — Non-latin-1 document filename crashes the markdown/HTML download endpoints  
  `src/docforge/app/backend/routers/explorer/views.py:96`
- [ ] **🟠 MOYENNE** · `consistency` — Three contradictory stories about raw chunk text; the raw text is in fact not recoverable  
  `src/docforge/worker/backend/libs/persistence/translator.py:7`
- [ ] **🟠 MOYENNE** · `bug` — Translator fabricates a successful CLASSIFY enrichment row for every figure even when no classifier ran  
  `src/docforge/worker/backend/libs/persistence/translator.py:143`
- [ ] **⚪ FAIBLE** · `design` — BlobNormalizer.__heal catches AttributeError/TypeError/KeyError broadly, converting engine regressions into 'reset your pipeline' 422s  
  `src/docforge/shared/libs/pipelines/ingest/stages/normalizer.py:128`
- [ ] **⚪ FAIBLE** · `consistency` — Caption folding rules diverge between the chunker projection and the generated md/html views  
  `src/docforge/shared/libs/pipelines/ingest/linearize/base.py:80`
- [ ] **⚪ FAIBLE** · `consistency` — Low-severity smells: undocumented bbox semantics in the IR API model, magic 'header_footer' string, header-less markdown tables, shared mutable pageless Provenance  
  `src/docforge/app/backend/routers/explorer/models_ir.py:23`
- [ ] **⚪ FAIBLE** · `bug` — Read paths crash on unknown stored block_type/role values (forward-compat gap the VARCHAR design explicitly invites)  
  `src/docforge/app/backend/routers/explorer/ir_adapter.py:104`

### Middlewares HTTP

- [ ] **🟠 MOYENNE** · `design` — A crashed original execution wedges its Idempotency-Key with 409s for up to TTL+GC (~25h) — staleness never checked on the in-progress path  
  `src/docforge/app/backend/libs/idempotency/middleware.py:211`
- [ ] **🟠 MOYENNE** · `bug` — Idempotency response cache is unbounded — IDEMPOTENCY_MAX_BODY_BYTES enforced on the request only, contradicting its own config doc  
  `src/docforge/app/backend/libs/idempotency/response_buffer.py:25`
- [ ] **🟠 MOYENNE** · `divergence-doc` — POST-shaped read endpoints (search, corpus query, estimate) are audited — docs promise 'reads are never audited', and the trail keeps rows forever by default  
  `src/docforge/app/backend/libs/audit/helpers.py:49`
- [ ] **⚪ FAIBLE** · `design` — Audit trail gaps grouped: keyed requests are audited BEFORE the client gets the response; unhandled non-HTTPException escapes skip the audit row; 401/429 attempts leave no trail  
  `src/docforge/app/backend/libs/audit/middleware.py:79`
- [ ] **⚪ FAIBLE** · `consistency` — Metrics blind spots grouped: idempotency replays/rejections and gate short-circuits all collapse into path=__unmatched__; SSE streams skew the latency histogram  
  `src/docforge/app/backend/libs/metrics/http_middleware.py:94`
- [ ] **⚪ FAIBLE** · `consistency` — Replay fidelity + doc drift grouped: replayed responses lose all original headers except content-type; two config/code-summary comments misstate behavior  
  `src/docforge/app/backend/libs/idempotency/middleware.py:225`

### Moteur graphe

- [ ] **🟠 MOYENNE** · `design` — Bindings on unknown slot names are silently ignored by validator, resolver and editor alike  
  `src/docforge/shared/libs/pipelines/validation/rules/child.py:58`
- [ ] **🟠 MOYENNE** · `bug` — Switch exhaustiveness check skipped when a node has only one WhenEquals edge  
  `src/docforge/shared/libs/pipelines/validation/rules/routing.py:95`
- [ ] **⚪ FAIBLE** · `consistency` — AutoWire types a foreach's items from its FIRST terminal only, diverging from the validator's uniformity rule  
  `src/docforge/shared/libs/pipelines/edit/wiring.py:122`
- [ ] **⚪ FAIBLE** · `design` — Engine escape hatches crash execute() without a FAILED record, contradicting its own record-not-crash contract  
  `src/docforge/shared/libs/pipelines/engine/core.py:421`
- [ ] **⚪ FAIBLE** · `bug` — ForEach body-group ids are excluded from the id-uniqueness scans (mint, fragment remap)  
  `src/docforge/shared/libs/pipelines/edit/topology.py:78`
- [ ] **⚪ FAIBLE** · `divergence-doc` — IoSlot.required is never derived from the field's optionality — describe() reports every slot required  
  `src/docforge/shared/libs/pipelines/base/node.py:196`
- [ ] **⚪ FAIBLE** · `consistency` — Minor engine/runtime smells (grouped): spurious ScoreBelow warning on failures, stale FromFirst comment, list-content LLM answers  
  `src/docforge/shared/libs/pipelines/engine/navigation.py:87`
- [ ] **⚪ FAIBLE** · `test-gap` — No test covers single-edge switch exhaustiveness or SetAfter on a convergence node  
  `src/docforge/tests/units/validation/test_validation_codes.py:1`
- [ ] **⚪ FAIBLE** · `consistency` — RemoveNode heals bindings but leaves a sibling ForEach's 'over' pointing at the removed node  
  `src/docforge/shared/libs/pipelines/edit/editor.py:167`
- [ ] **⚪ FAIBLE** · `consistency` — Retry-count semantics drift across the retry implementations (grouped lows)  
  `src/docforge/shared/libs/pipelines/nodes/embed/base/node.py:129`
- [ ] **⚪ FAIBLE** · `bug` — SetAfter silently deletes ALL incoming edges of a convergence node, producing a valid-but-wrong graph  
  `src/docforge/shared/libs/pipelines/edit/editor.py:199` _(aussi: pipelines-api)_

### Pipeline ingest

- [ ] **🟠 MOYENNE** · `bug` — Classified-mode fail-soft drops the stamped kind and OCR read — PIPELINE.md promises 'VLM KO → kind conservé'  
  `src/docforge/shared/libs/pipelines/ingest/stages/enrich_body.py:297`
- [ ] **🟠 MOYENNE** · `bug` — Docling bbox normalization neither clamps to [0,1] nor guards the page-size fallback — violates the Provenance contract pp_structure honors  
  `src/docforge/shared/libs/pipelines/ingest/nodes/parse/parser/docling/helpers.py:96`
- [ ] **🟠 MOYENNE** · `design` — Layout view mis-attributes table content and carried-heading ids in segmentChunkText  
  `src/docforge/app/frontend/src/features/explorer/layout/chunkAssembly.ts:37`
- [ ] **🟠 MOYENNE** · `divergence-doc` — PIPELINE.md chunk section stale on three points vs shipped code  
  `src/docforge/PIPELINE.md:289`
- [ ] **🟠 MOYENNE** · `divergence-doc` — PIPELINE.md contextualize/llm config table lists endpoint fields the method config no longer has (P6 externalization not reflected in the table)  
  `src/docforge/shared/libs/pipelines/ingest/nodes/contextualize/llm/config.py:18`
- [ ] **🟠 MOYENNE** · `divergence-doc` — PIPELINE.md enrich topology stale: 'vlm scanned' complement node does not exist; scanned_text is OCR-only; thresholds differ  
  `src/docforge/PIPELINE.md:222`
- [ ] **🟠 MOYENNE** · `divergence-doc` — PIPELINE.md intake stage stale: pdf_probe max_pages ceiling, IntakeResult extra fields, source_probe slot, html/md preview channel  
  `src/docforge/shared/libs/pipelines/ingest/nodes/intake/pdf_probe/core.py:26`
- [ ] **🟠 MOYENNE** · `divergence-doc` — PIPELINE.md scan doctrine contradicts code: do_ocr defaults to True, doc mandates 'do_ocr=false toujours'  
  `src/docforge/shared/libs/pipelines/ingest/nodes/parse/parser/docling/config.py:20`
- [ ] **🟠 MOYENNE** · `bug` — Retry stacking: VLM and embed openai_compatible leave the SDK client at its default 2 retries under their own hand-loops  
  `src/docforge/shared/libs/pipelines/nodes/vlm/openai_compatible/core.py:66`
- [ ] **🟠 MOYENNE** · `perf` — Unbounded rowspan/colspan expansion in the PP-Structure table flattener can hang/OOM the worker  
  `src/docforge/shared/libs/pipelines/ingest/nodes/parse/parser/pp_structure/table.py:123`
- [ ] **🟠 MOYENNE** · `design` — Uniform→classified round-trip silently drops the per-class VLM chains (classes route to zero-spend skip without a notice)  
  `src/docforge/shared/libs/pipelines/ingest/stages/reader.py:179`
- [ ] **🟠 MOYENNE** · `divergence-doc` — doc_meta contextualizer diverges from PIPELINE.md: single title anchor, not 'all declared metadata', different config surface  
  `src/docforge/shared/libs/pipelines/ingest/nodes/contextualize/doc_meta/core.py:19`
- [x] **⚪ FAIBLE** · `bug` — Cost estimate treats paddle as the paid OCR representative, hiding a hosted escalation tail  
  `src/docforge/shared/libs/pipelines/ingest/estimate/plan.py:93`
- [ ] **⚪ FAIBLE** · `bug` — Degenerate heading-only document produces zero body chunks — all titles dropped  
  `src/docforge/shared/libs/pipelines/ingest/nodes/chunk/base/node.py:124`
- [ ] **⚪ FAIBLE** · `consistency` — Gotenberg _preview bypasses the shared NetworkRetry that _convert uses  
  `src/docforge/shared/libs/pipelines/ingest/nodes/intake/converter/gotenberg/core.py:157`
- [ ] **⚪ FAIBLE** · `consistency` — Language detection: per-document, cheap; minor tie/window/regex quirks  
  `src/docforge/shared/libs/pipelines/ingest/nodes/parse/parser/base/language.py:265`
- [ ] **⚪ FAIBLE** · `consistency` — Overlap semantics soft spots: cap overshoot, missing validator, 'same section only' claim  
  `src/docforge/shared/libs/pipelines/ingest/nodes/chunk/fixed_size/core.py:73`
- [ ] **⚪ FAIBLE** · `divergence-doc` — PIPELINE.md inventory drift (grouped): missing paddle OCR, deliver/, vlm_entry, parser bricks in tree, structgen, UNIQUE list, read_text naming, chunker defaults/knobs, /embed_all; architecture.md still says preflight 'reste à ajouter'  
  `src/docforge/PIPELINE.md:51`
- [ ] **⚪ FAIBLE** · `perf` — Semantic chunker fires one unbatched-by-us embedding call over every context window  
  `src/docforge/shared/libs/pipelines/ingest/nodes/chunk/semantic/core.py:118`
- [ ] **⚪ FAIBLE** · `consistency` — Stale/false in-code comments and style nits (grouped)  
  `src/docforge/shared/libs/pipelines/ingest/pipeline.py:112`
- [ ] **⚪ FAIBLE** · `consistency` — Table flattening edge-case smells (header heuristic, nested tables, span double-booking, unclosed cells)  
  `src/docforge/shared/libs/pipelines/ingest/nodes/parse/parser/pp_structure/table.py:164`
- [ ] **⚪ FAIBLE** · `bug` — Web-chrome per-block signal can demote a document HEADING titled 'Menu'/'Search'  
  `src/docforge/shared/libs/pipelines/ingest/nodes/chunk/base/passages.py:225`
- [ ] **⚪ FAIBLE** · `consistency` — pp_structure mapper robustness: sidecar-supplied ids, inconsistent defaults, shared mutable pageless Provenance  
  `src/docforge/shared/libs/pipelines/ingest/nodes/parse/parser/pp_structure/mapper.py:119`

### Search & retrieval

- [ ] **🟠 MOYENNE** · `divergence-doc` — PIPELINE.md claims search does not query chunk-scope semantic field vectors — the read side is wired  
  `src/docforge/PIPELINE.md:427`
- [ ] **🟠 MOYENNE** · `design` — Rewrite/HyDE provider endpoints invisible to health/preflight, and their degrade is invisible to callers  
  `src/docforge/shared/libs/pipelines/search/nodes/query/base.py:92`
- [ ] **🟠 MOYENNE** · `divergence-doc` — Search blobs have no BlobNormalizer/auto-heal path — registry drift bricks stored search graphs  
  `src/docforge/app/backend/libs/search/service.py:59`
- [ ] **🟠 MOYENNE** · `divergence-doc` — Typed search failure modes (424/503/504, score_kind, range filters) undocumented in rest-api.md  
  `docs/rest-api.md:876`
- [x] **🟠 MOYENNE** · `bug` — limit > top_n silently truncates rerank-enabled results to 50 hits  
  `src/docforge/shared/libs/pipelines/search/nodes/rerank/cross_encoder/config.py:37`
- [ ] **⚪ FAIBLE** · `dead-code` — Minor smells: dead flags/language fields, stale docstrings, private embedder-hook access, unbounded disabled-doc must_not list  
  `src/docforge/shared/libs/public_models/search/query.py:56`
- [ ] **⚪ FAIBLE** · `consistency` — score_kind mislabels degraded reranks; read port's "hydrated exactly once" claim is stale on the rerank path  
  `src/docforge/app/backend/routers/search/helpers.py:56`

### Télémétrie

- [ ] **🟠 MOYENNE** · `bug` — 'Errors & warnings' LogQL panels miss all WARNING-level app/worker logs  
  `services/telemetry/grafana/dashboards/docforge-logs.json:63`
- [ ] **🟠 MOYENNE** · `perf` — Loki has no retention configured — unbounded log growth on a 23GB VM  
  `services/telemetry/loki-config.yml:6`
- [ ] **⚪ FAIBLE** · `consistency` — Grouped low-severity smells in dashboards and promtail/loki configs  
  `services/telemetry/grafana/dashboards/docforge-overview.json:201`
- [ ] **⚪ FAIBLE** · `divergence-doc` — Stale dashboard descriptions: 'one starter dashboard' / wrong overview title  
  `compose/overlays/telemetry.yml:23`

### Worker & jobs

- [ ] **🟠 MOYENNE** · `consistency` — Enqueue-failure handling inconsistent: upload and single reingest can leave a forever-PENDING job no reaper covers  
  `src/docforge/app/backend/routers/documents/router.py:200`
- [ ] **🟠 MOYENNE** · `dead-code` — Enrichment attempt trace and entity mentions are never persisted — the tables, read APIs and export path are write-dead on ingest  
  `src/docforge/worker/backend/libs/jobs/core.py:188`
- [ ] **🟠 MOYENNE** · `bug` — No guard against two concurrent runs of the same document — interleaved Qdrant delete/upsert can strand orphan points  
  `src/docforge/app/backend/routers/documents/router.py:260`
- [ ] **🟠 MOYENNE** · `perf` — Re-ingest leaks superseded blobs: save() replaces rows but never orphan-purges the previous run's S3 objects  
  `src/docforge/shared/libs/services/db/facades/ingestion_facade.py:161`
- [ ] **⚪ FAIBLE** · `bug` — Job observability accuracy gaps: cut-stage usage lost from the cost meter, stale breadcrumb/counter on retried attempts, progress denominator counts never-run escalation roots  
  `src/docforge/worker/backend/libs/jobs/progress.py:149`
- [ ] **⚪ FAIBLE** · `dead-code` — Minor smells: dead non-dict blob branch, worker entrypoint imports backend before config, relevance score dropped  
  `src/docforge/worker/backend/libs/jobs/core.py:163`
- [ ] **⚪ FAIBLE** · `divergence-doc` — architecture.md claims the per-collection budget rides arq `_job_timeout` at enqueue — arq has no such kwarg and the code deliberately does otherwise  
  `.claude/rules/architecture.md:37` _(aussi: test-bodies)_
- [ ] **⚪ FAIBLE** · `divergence-doc` — page.is_scanned hardcoded False and source_kind/simhash never written by a run, vs PIPELINE.md's decided derivation-at-persistence  
  `src/docforge/worker/backend/libs/persistence/translator.py:317`

### Hygiène logs

- [ ] **⚪ FAIBLE** · `consistency` — Grouped lows: uvicorn access/error logs bypass loggerplusplus (no cid, off-format), and rate-limit failure log includes a client-controlled XFF-derived key  
  `src/docforge/app/Dockerfile:118`
