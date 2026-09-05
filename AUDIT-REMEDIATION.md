# DocForge — Remédiation de l'audit v0.14.0

> Chantier de mise à plat suite à l'audit du 2026-09-04 (`main @ 0162c70`). Rapport complet: https://claude.ai/code/artifact/1f51943f-6e30-4e4f-9906-ceca159cb457

**247 points uniques** — 25 haute · 107 moyenne · 115 faible. Traités par vague, par ordre de sévérité. `[ ]` à faire · `[x]` fait · `[~]` en cours.

> Base : tout le travail des vagues ci-dessous est **mergé sur `main` et livré jusqu'à `0.14.8`** (chaque vague = un tag `v0.14.x` + Release GitHub). Les buckets de vague sont indicatifs (heuristiques) ; la séquence V1→V8 faisant autorité est celle du rapport. Chaque tranche est commitée + vérifiée (ruff + pytest units) avant la suivante. Un WIP inachevé (backend-atomicity + caps lectures) est parké hors-main sur `fix/audit-backend-atomicity`.

## Journal

- **2026-09-05 — Vague E / 0.14.15 (V8 infra + bge_server, 11 items, 2 agents ||)** : **infra/compose (7)** — (1) **healthcheck `docforge_app`** : `GET /health` (public, hors `/api/v1`, zéro I/O) via `python -c urllib` (pas de curl dans l'image slim) ; `docforge_mcp` + `docforge_caddy` passent `depends_on: service_healthy` sur l'app. (2) **`.dockerignore` manquant** : `src/docforge/.dockerignore` créé (le contexte app/worker est `src/docforge/`, PAS `src/` — Docker ne lit `.dockerignore` qu'à la racine du contexte) → exclut `.venv` (~400 Mo), `node_modules`, `dist`, `.vite`, caches ; **safe** car l'image app build son propre `dist/` in-container (stage `ui-build` `npm ci`+`npm run build`, vérifié). (3) **Grafana pw drift** : export mort `GRAFANA_ADMIN_PASSWORD` retiré du Makefile + bloc `.env.example` racine réécrit vers `services/telemetry/.env` (mécanisme réel `env_file`). (4) **compose/README** : faux dir `compose/telemetry/` → `services/telemetry/` + règle path proxy/telemetry (`-f`, résolue depuis project dir) corrigée. (5) **headers dev.yml/gpu.yml** : exemples `-f` manuels (paths hors-repo) → pointent les fichiers-scénario ; claim "last-include wins" → FIRST-wins. (6) **robustesse** : `docforge_app` attend seaweedfs healthy ; healthchecks promtail/grafana + `deploy.resources.limits` sur les 4 services télémétrie + depends_on service_healthy. (7) **commentaires legacy** purgés (base.yml). Validé : `config -q` sur les 16 combos (4 scénarios × {none,proxy,telemetry,both}). **bge_server (4)** — (1) **`/embed_all` back-pressure** : compteur in-flight capé dans `BatchingEngine` → `QueueFullError` → **503 + Retry-After** au routeur (comme les 4 routes queued), plus d'OOM possible. (2) **thread-budget** : réconcilié avec le moteur 2-locks (embed+rerank = 2 forward passes concurrents) — doc/code cohérents. (3) **`/rerank` tri score-descendant** (parité TEI) — le client docforge `bge_reranker` remappe par `index` (vérifié), donc sûr. (4) **cluster doc/commentaires stale** (worker/engine/context/lifespan : "3 workers/1 lock" → "4 workers/2 locks"). Gate bge : format+lint+mypy clean, **33 passed** (+4). Reste V8 model-servers : les 4 items **paddle** (wave dédiée). **→ V8 : 52/188.**

- **2026-09-05 — Vague V7 (documentation, 11 items — pas de release : docs non packagées)** : passe doc↔code, agent dédié, **claims re-vérifiés contre le code**. Ground truth relu depuis `NodeRegistry` (familles + kinds). Fixes (tracked) : PIPELINE.md (deliver/bundle ajoutés à l'arbre + phrase familles ; statuts stale corrigés — block-id remap shippé, caveat item-index à jour, arbre +granite_docling/pp_structure/vlm_entry, nodes +structgen) ; README (+release-images.yml) ; rest-api.md (SearchHit/JobStatus/JobPage pagination alignés sur les response models) ; architecture.md (13 ressources SDK, gate frontend eslint+tsc+vitest+build, note rename supprimée) ; brand.md (`--text-mute` = `#6e6960` réel, pas `#8a8378`) ; deployment-resources.md (flag stale ~10/8 GB retiré — getting-started dit déjà ~20 GB/12-16 GB) ; getting-started.md (port range 10040–10052 + ligne paddle 10049 ; field-types 6→**11** depuis l'enum `FieldType`). **Déjà OK** (finding stale) : python-sdk.md liste déjà CREATE. **Local-only (gitignored, hors commit)** : CLAUDE.md familles+tests (comme `.claude`) — noté, appliqué localement. Aucun code/test/compose/.github touché. **→ V7 : 21/21 (0 restant).** NB : pas de tag/release — les docs ne sont pas packagées dans les images/SDK, un rebuild d'images identiques serait du gaspillage ; commit docs sur main.

- **2026-09-05 — Vague D / 0.14.14 (V1 deps ML : 1 MOYENNE + 1 FAIBLE)** : (torch) **GPU cu124 EOL → cu128** (décision utilisateur) — l'index wheel `pytorch-cu124` était figé (aucun torch >2.6 n'y sort), gelant les images GPU. Index renommé `pytorch-cu128` (URL `whl/cu128`) dans `docforge` + `bge_server` (sources + [[tool.uv.index]] + commentaires) ; `uv lock` re-résout **torch 2.6.0+cu124 → 2.11.0+cu128** (torchvision 0.26.0+cu128) sur les deux projets, chaîne nvidia-cu12 alignée 12.8. CPU **inchangé** (2.12.1+cpu / 2.13.0+cpu). Refs de version mises à jour dans worker/Dockerfile, bge Dockerfile + README. **⚠️ Non validable sur cette VM (pas de GPU) — ships unvalidated on GPU hardware jusqu'à un déploiement GPU testé** (caveat assumé par l'utilisateur). (transformers) **pin `<5`** — le re-lock a déjà tiré la **dernière 4.x (4.57.6)** sur les deux (capture les fixes de la ligne 4.x) ; le plafond `<5` reste un **WONTFIX justifié+documenté** (FlagEmbedding/FlagReranker exige l'API tokenizer 4.x supprimée en 5.x — commentaire pyproject déjà en place) : les fixes 5.x-only ne sont pas prenables tant que FlagEmbedding ne supporte pas transformers 5. Validé : `uv lock --locked` OK (0 drift) × 2, docforge 1425 passed + ruff clean, bge 29 passed + ruff clean ; 0 ref cu124/2.6.0 hors locks. **→ V1 : 2 `[ ]` restants, tous deux `.claude/` gitignorés (hook-log secrets + settings bypassPermissions) — hors release versionnée.**

- **2026-09-05 — Vague C / 0.14.13 (V1 durcissement FAIBLE : 5 items, 2 agents ||)** : (1) **bypass rate-limit auth-failure** (app.py:86 — moitié XFF déjà close en 0.14.10) — le limiteur proper est INNER du gate auth, donc un 401 court-circuite avant lui : un flood mauvais-credentials n'était jamais throttlé. `RateLimitEngine` extrait (`ratelimit/engine.py`, `allow()` fail-open + `reject()` 429+Retry-After, réutilisé par les 2 gates) ; `AuthMiddleware.__reject_auth_failure` throttle le chemin d'échec par IP (`authfail:<ip>`, honore `RATE_LIMIT_TRUST_FORWARDED_FOR`) → 429 au-delà du budget, sinon le 401 opaque verbatim. Option (b) choisie (garder l'ordre) car le keying per-key exige le principal injecté par Auth ; cycle d'import `auth→ratelimit` cassé via `TYPE_CHECKING` dans `keying.py`. **Exemption job-poll/SSE volontairement NON appliquée** sur ce chemin (un échec-auth n'est jamais un poll légitime). OFF par défaut. **Revu par `code-reviewer` : APPROVED** (6 checks passés ; 2 INFO tradeoffs bornés derrière 2 flags off-by-default) → note runbook ajoutée (PROD-HARDENING §9). (2) **workflow least-privilege** (ci.yml:20) — `permissions:` explicites : floor `contents: read` sur ci/gate/release-* ; `packages: write` scoped au seul job `images`, `id-token: write` au seul job `publish` (PyPI OIDC) ; `gate.yml` capé `contents: read` (intersection caller∩callee → ne peut plus hériter `packages: write`). 9 actions **pinnées au SHA** dans release-images/release-sdk (SHA↔tag **vérifiés par moi** via `gh api`, dont la déréférence du tag annoté pypi-publish → commit exact ; zéro changement de version). Topologie 2-workflows intacte (PyPI trusted-publishing lie le nom de fichier). Trivy = table→artefact (pas de SARIF → pas de `security-events`), job non-bloquant. (3) **overlay télémétrie** (telemetry.yml:84) — ports grafana/prometheus/loki bindés `${TELEMETRY_BIND_ADDR:-127.0.0.1}` (loopback par défaut au lieu de `0.0.0.0`) + knob/commentaires ; creds Grafana déjà via env-file `change_me`. `config -q` OK sur prod-cpu/gpu×télémétrie(±proxy). (4+5) **whoami scope-gate résidu** (whoami.py:40) + **hardening smells groupés** (blobs/router.py:45) — **déjà clos** (vérifié par l'agent) : blob headers nosniff/attachment/CSP-sandbox + 403 (pas 404) sur blob étranger, redaction export via `redact_blob_secrets`, whoami dégrade en 403 ; seul résidu = "MCP client cache", **hors scope backend** → suivi sous l'item V8 `scoped_sdk.py`. +tests rate-limit (5). **1425 passed**, ruff clean × 4 projets. **→ V1 : 4 `[ ]` restants (torch cu128 → Vague D ; transformers<5 ; 2× .claude gitignored).**

- **2026-09-05 — Vague B / 0.14.12 (V1 import : 1 MOYENNE + 1 FAIBLE, clôt les 2 derniers `[~]`/import de V1)** : (B1) **scope-grant créateur à l'import** (clôt le `[~]` — le gate CREATE était déjà là) — un import crée la collection dans le WORKER, or `grant_creator_scope` (app-side) a besoin du `principal.key`. La logique d'append est extraite dans la façade store `AuthFacade.grant_collection_to_key(key_id, collection_id) -> bool` (lit la clé → no-op sur wildcard/duplicate/NULL-perms/absente → append+persist ; opère sur le JSONB brut, **aucun import du modèle app**) ; `grant_creator_scope` y délègue (ne garde que le guard principal-level app-side). Le `key_id` créateur est threadé `import router → enqueue_import(...,granting_key_id) → tâche worker` (ids/scalaires only) et appliqué **après `mark_done`** en best-effort (`_grant_imported_collection` : swallow+warn — la collection existe déjà, un échec de grant ne doit pas rater un import DONE ; root répare le scope). None pour un caller full-access/keyless. (B2) **validation fail-fast des blobs importés** — l'importer copiait `pipeline`/`search` verbatim (seul write path sans validation). Extrait un socle **worker-safe** dans `shared_libs.pipelines.validation` : `SearchResultContract` (contrat terminal SearchResult, lu sur les faces `Produces` statiques, zéro exécution) + `BlobStructureValidator` (build + `GraphValidator` [+ terminal pour search] → `BlobValidationError`). L'importer appelle `_validate_contract_blobs(contract)` **AVANT** `create_collection` → `CollectionImportError` nommant le blob fautif (pipeline vs search) ; `{}` search = défaut stock, laissé tel quel. Dedup app **behavior-preserving** : `search_blob_validation.py` délègue son check terminal à `SearchResultContract` (~50 lignes dupliquées retirées, messages/codes 422 inchangés — `test_collections_search_blob.py` passe sans modif). +tests B1 (façade append/no-op ×4 ; worker grant/skip/swallow ×3) + B2 (pipeline/search/topology malformés rejetés ×3, bundle valide + search `{}` OK) ; conftest transfer porte un `IngestPipeline.light_blob()` valide. Agent `backend` dédié, **vérifié par moi** (imports importer + gate rejoué). **1420 passed**, ruff check+format clean. **→ V1 : 0 `[~]`, 9 `[ ]` restants (tous FAIBLE/MOYENNE non-import).**

- **2026-09-05 — Vague A / 0.14.11 (V1 hygiène log/error : 1 MOYENNE + 2 FAIBLE)** : trois findings du chemin log/erreur où une chaîne non fiable atteignait un log ou une surface d'erreur. (1) **Log injection** (documents/router.py:201) — nouveau `LogSafeHelpers.sanitize` (`app/backend/libs/logsafe/`) : strip C0/C1 (CR/LF/tab → anti log-splitting), collapse whitespace, cap 256, placeholder `<empty>` ; câblé sur les noms/filenames user-controlled loggés (upload filename, collection name, api-key name). Miroir de `RequestIdHelpers._sanitise` mais pour du free-text. (2) **Redaction exceptions provider** (worker jobs/core.py:299 + health sweep) — `ConfigDumpHelpers.redact_text` (extrait le redactor userinfo `scheme://user:pass@` déjà utilisé par `masked`, exposé en public) appliqué à `job.error` avant persistance ET au `ReachabilitySweep.__detail`/champ `endpoint` (base_url redacté à la surface, l'allowlist matche toujours sur le RAW url intact) : un base_url credential-bearing ne fuit plus dans job.error/health/preflight ; message par ailleurs préservé (valeur diagnostique). (3) **whoami 500→403** (whoami.py) — un blob permissions malformé dégrade désormais en `403 "API key has malformed permissions."` **identique** au gate authz (`AuthzGuard.__parse`), plus de `ValidationError` non gérée transformée en 500 par `auto_handle_errors`. +tests : `test_logsafe.py` (5, sous api/ car dépend du fixture `fastapi_app`), `test_config_dump.py` (+2 redact_text), `test_auth.py` (+3 whoami : root full-access, scoped grants, malformed→403 — l'endpoint avait 0 test, clôt aussi ce test-gap V8). **1408 passed**, ruff check+format clean. NB : le finding V1 groupé `whoami.py:40` (500-instead-of-4xx + scope-gate edge cases) a sa moitié 500 close ici ; le résidu scope-gate reste `[ ]`.

- **2026-09-04 — XFF non-trusté par défaut (V1 FAIBLE) + clôture `[~]` import** : `RATE_LIMIT_TRUST_FORWARDED_FOR` passe **default `true`→`false`** — le déploiement out-of-box (prod-cpu) n'a pas de proxy, donc un XFF client-fourni était forgeable (spoof du keying rate-limit IP en auth-off) ; défaut sûr = keying sur le peer transport, `true` seulement derrière un proxy qui **réécrit** XFF (overlay Caddy). `keying.py` prend déjà `trust_forwarded_for` (aucun changement de logique). Docs alignées (configuration.md, PROD-HARDENING.md). Les 2 tests de keying passent (flag explicite, indépendants du défaut). Par ailleurs le `[~]` **import exhaustion (bomb + buffering)** est confirmé **entièrement clos par 0.14.7** (guards `IMPORT_MAX_DECOMPRESSION_RATIO`/`_MEMBERS` + import streamé 64 MiB) → passé `[x]`. NB : la moitié "unauth bypass" du finding jumeau (app.py:86) reste `[ ]` (à confirmer dans le middleware, non tracé ici).

- **2026-09-04 — Exclusion search bornée (475) + fix runtime latent** : la liste d'exclusion des docs désactivés (`must_not document_id in {disabled}`) était non bornée et ridait CHAQUE requête. Désormais bornée par `SEARCH_MAX_DISABLED_DOC_EXCLUSIONS` (2000) : sous le cap = must_not classique ; au-delà = **flip vers une inclusion positive `document_id in {enabled}`** (le set plus petit sur une collection majoritairement archivée), lu via `list_disabled_ids(limit=cap+1)` pour détecter le débordement sans charger tout. ⚠️ Le sous-agent avait référencé `DocumentApi.list_disabled_ids(limit=...)` (param inexistant) + `list_enabled_ids` (méthode inexistante) — bug runtime masqué par les tests serviceless qui mockent DocumentApi (le piège connu) ; **corrigé** (ajout du param + de la méthode) + test du flip past-cap. `1398 passed`. NB : les 3 autres findings de la vague (306 lectures bornées, 308 PATCH atomique, 473 toggle cross-store) NON faits par l'agent (scope trop large, épuisé en exploration) — restent `[ ]`, vagues dédiées à suivre.

- **2026-09-04 — Vague frontend Layout tab (6 MOYENNE)** : (A) **erreur chunks blanchissait tout l'onglet Layout** — `chunksError` propagé à LayoutTab → degrade non-bloquant (page/IR rendus + notice « provenance chunk indisponible »), conforme au design degrade-without-chunks. (B) **brand <11px** — `fontSize 9` remplacé par token ≥11px ; grep 0-hex/0-sub-11px propre sur tout `layout/`. (C) **ETA jamais décrémentée** — le filtre testait `TERMINAL` (enum job-level `done/failed/cancelled`) contre `event.status` (enum node-level `success/failed/skipped/running`), donc un stage `success` n'était JAMAIS compté fini → ETA figée. Nouveau set `EVENT_FINISHED={success,failed,skipped}`. (D) **Layout eager** — recompute par-render mémoïsé + fetch gardé (plus de refetch total à chaque switch d'onglet) + chargement d'images de page allégé. (E) **caches par-document jamais reset** — quand `documentId` change sans remount, les caches (pages/ir/chunks/provenance/lightbox) montraient les données du document PRÉCÉDENT ; corrigé par le pattern React « reset-state-during-render » (garde `documentId !== cached` en render, pas un `useEffect` qui racerait l'effet d'activation d'onglet sur closure stale). (F) **Search Lab** — `queryDocuments(limit:1)` + `res.total>0` au lieu de tirer tout le corpus non-paginé pour un booléen. Gate conteneur vert : lint 0-err, tsc 0, vitest 2, build ✓. Aucune régression.

- **2026-09-04 — Vague fiabilité transfert/import (3 MOYENNE)** : (497) **export non snapshot-consistent** — l'export re-query les hashes de blobs en LIVE après la passe documents ; un delete/reingest concurrent produisait un bundle qui échoue à l'import ou perd des données silencieusement. Désormais le set de blobs est dérivé des MÊMES lignes documents écrites (snapshot self-consistent), et un blob référencé disparu **abort bruyamment** (`CollectionExportError` nommant le document) — jamais de bundle silencieusement lossy. Choix snapshot+abort plutôt que tx repeatable-read (l'export lit sur N sessions courtes, pas de tx unique ; tenir une longue tx pinnerait PG). (499) **hard-kill → transfert RUNNING éternel** — nouveau cron `reap_stuck_transfers` (sibling du reaper de jobs, `WORKER_REAP_ENABLED`) : marque FAILED tout transfert RUNNING dont `updated_at` a gelé au-delà de `WORKER_TRANSFER_REAP_STALE_SECONDS` (défaut 10800s, validé au boot `>= job_timeout ceiling`) → row terminal + bundle stagé GC-reclaimable. **Pas de migration** (réutilise `updated_at`). Résidu documenté : un IMPORT SIGKILL mid-restore peut laisser une collection à moitié importée (orphan supprimable ; le row n'a pas l'id collection avant `mark_done`, donc pas de rollback propre — 2-phase hors scope). (501) **import bufferisait tous les blobs en RAM** (jusqu'à 5 GiB) — désormais streamé par budget-octets (64 MiB, un blob tient toujours) : flush batch → S3+registry → release, mémoire bornée à ~un batch (comme l'export). Guards decompression-bomb intacts. +tests (abort export si blob disparu row/objet ; reap stale→FAILED, fresh intact, no-op si disabled ; import flush >1× et pic < total). `1397 passed`, ruff clean.

- **2026-09-04 — 🔴 REVERT release restructure (0.14.5 a cassé la release) → 429/437 déférés** : le run `release.yml` de v0.14.5 a échoué sur DEUX bugs de mon restructure : (1) **SDK/PyPI** — `Invalid attestations ... release.yml@refs/tags/v0.14.5 does not match expected Trusted Publisher (release-sdk.yml)` : **PyPI Trusted Publishing ne supporte PAS les reusable workflows** (le commentaire de l'agent affirmait le contraire — faux) ; PyPI matche le workflow **top-level**, donc release-sdk.yml DOIT rester déclenchée directement sur le tag. (2) **promote-latest** — `repository name (Florian-BARRE/docforge-app) must be lowercase` (owner non minusculé dans `imagetools create`). Comme 429 (gate unique) exige de wrapper release-sdk.yml en reusable — incompatible PyPI — il est **non résoluble** sans reconfig PyPI côté compte user. Décision : **revert complet** des 5 workflows à l'état 0.14.4 connu-fonctionnel (release.yml supprimé ; release-images.yml + release-sdk.yml re-top-level, chacun gate). **429 + 437 re-ouverts/déférés** (437 était couplé au restructure). **435 conservé** (docs set_version/alignment, indépendant). Le gate + les 8 images de 0.14.5 étaient verts — seuls `:latest` (pas bougé, l'effet voulu de 437 par accident) et le SDK PyPI (pas publié) ont raté ; 0.14.6 rattrape. Voir mémoire `release-gate`.

- **2026-09-04 — Vague durcissement release/CI (1 MOYENNE + 2 FAIBLE)** : (429) **gate joué 2× par tag** — release-images.yml et release-sdk.yml faisaient chacun `uses: gate.yml`, donc un tag `v*` relançait tout le gate monorepo deux fois en parallèle. Nouveau `release.yml` = **orchestrateur unique** sur `v*`/`sdk-v*` : `gate` une seule fois → fan-out `images` (si `startsWith(ref,'v')`) + `sdk`, tous deux `needs: gate` (un gate rouge bloque toujours les DEUX publish) ; les 2 anciens workflows passent en `workflow_call`-only (plus de trigger tag direct) — noms de fichiers conservés car le Trusted-Publishing PyPI matche le fichier de la reusable workflow. (437) **fenêtre de publication partielle** — `:latest` déplacé dans un job `promote-latest` séparé `needs: images` (tout le matrix) : un échec d'une image laisse `:latest` sur la release précédente au lieu de le bouger sur une publication incomplète. (435) **couverture versions** — set_version.sh + test_version_alignment.py documentent explicitement l'exclusion VOLONTAIRE de bge_server/paddle_server (sidecars à cadence propre) et du frontend package.json (`private:true`, jamais publié, lu par personne au build/runtime — inerte). Validé : 5 YAML parsent, set_version.sh `bash -n` OK, test alignement vert. ⚠️ La prochaine release (0.14.5) est la 1re à utiliser `release.yml` — à surveiller.

- **2026-09-04 — Vague surface MCP/SDK (3 MOYENNE + 1 FAIBLE)** : (359) **surface MCP incomplète** — ajout des 2 tools manquants `collection_health` (sweep preflight zéro-dépense) + `reingest_collection` (bulk reingest collection-scope), wrappant des méthodes SDK existantes ; `docs/mcp.md` (2 lignes + compte 55→57) et le gate de compte (`EXPECTED_TOOL_COUNT`/`_NAMES`) alignés. (361) **erreurs API opaques** — nouveau `ErrorTranslatingFastMCP` qui enveloppe TOUS les tools (wrapper partagé, pas tool-par-tool) : un 4xx expose désormais le `detail` du body au LLM au lieu d'un code nu. (357) **guard lockstep aveugle** — `test_resource_parity` couvre enfin audit/corpus/snippets (une méthode ajoutée à un seul client casse le guard) + 3 nouveaux fichiers de tests unitaires (audit.list, corpus.query/bulk_reingest, snippets.export/apply — verbe+path+type sur async ET sync). (365) **cohérences** — `corpus` ajouté aux docstrings des 2 clients ; défaut `get_design` aligné `full=False` (async+sync) sur le défaut serveur/MCP (le SDK était l'outlier à `True`) ; aucun artefact dist 0.1.1 tracké (rien à purger). Gates locaux complets verts : mcp 48 (format+lint+mypy) · sdk 557 (+15, parity OpenAPI incluse). Corrigé 2 nits mypy/UP035 laissés par l'agent.

- **2026-09-04 — 🔴 Gate CI rouge depuis 0.14.1 → images/SDK JAMAIS publiées (fix release)** : le job `gate / docforge` lance `ruff format --check` (séparé de `ruff check` que je vérifiais en local) ; 20 fichiers docforge + 1 bge_server accumulés depuis les vagues HIGH « would reformat » → gate rouge → `release-images`/`release-sdk` (`needs: [gate]`) skippés pour **v0.14.1 ET v0.14.2** (rien de publié). `ruff format .` passé sur docforge + bge_server ; **gate complet rejoué en local sur les 4 projets** (docforge format+lint+1388 · bge_server format+lint+mypy+29 · sdk format+lint+mypy+542 dont parity OpenAPI · mcp format+lint+mypy+42) avant tag. Le piège était déjà en mémoire `release-gate` (item 3) — erreur d'exécution, pas de connaissance : désormais gate complet local obligatoire avant tout tag.

- **2026-09-04 — Vague robustesse store/admission (1 HAUTE-partiel clôturée + 1 MOYENNE)** : (A) **fuite bundles import échoués** (clôt le `[~]` HAUTE) — le GC transfert ne balayait que les EXPORT ; `list_expired` rendu kind-agnostic + la route import stampe un `expires_at` (`IMPORT_STAGING_TTL_SECONDS`=24 h) à l'admission → un import échoué/abandonné est reclamé (objet S3 + row) comme un export expiré. **Pas de migration** (`expires_at` déjà sur `CollectionTransfer`). (B) **races check-then-insert → 500** — deux fenêtres UNIQUE : upload concurrent du même `(collection, source_hash, version)` → `IngestionFacade.admit` attrape l'IntegrityError ciblée (`uq_document_collection_id`), rollback + re-query l'incumbent, renvoie la **réponse duplicate idempotente** (value-object `AdmissionResult`) au lieu d'un 500 ; nom de collection dupliqué concurrent → `DuplicateCollectionNameError` (match `uq_collection_name`) → **409** (comme le pré-check), plus de 500 driver. Noms de contrainte vérifiés contre la migration ; tout autre IntegrityError re-levé. +tests (GC balaie un import expiré ; upload concurrent = duplicate pas 500 ; nom dupliqué = 409). `1388 passed`.

- **2026-09-04 — Vague fiabilité cycle-de-vie data/blob (4 MOYENNE)** : (1) **garde reingest concurrent** — `IngestionFacade.reingest` verrouille la ligne document `FOR UPDATE` puis refuse (`ReingestOutcome.ALREADY_ACTIVE`) si un job PENDING/RUNNING existe déjà → route single = **409**, path bulk = skip ; deux runs parallèles n'interleavent plus leurs delete/upsert Qdrant (plus d'orphelins). (2) **purge blobs supersédés au reingest** — `save()` snapshote les hashes référencés AVANT le purge, flush, puis supprime ceux que plus rien ne référence (les renders/crops/PDF de l'ancien run ne fuitent plus en S3 ; source préservée). (3) **enqueue-or-mark-failed partagé** — nouveau `IngestEnqueuer` utilisé aux **3** sites (upload, reingest single, bulk) : un blip Redis marque le job FAILED (jamais un PENDING orphelin invisible du reaper) + 503 au caller. (4) **TOCTOU purge orphelins** — `find_unreferenced`+`delete_rows` remplacés par un unique `delete_unreferenced` (`DELETE … WHERE NOT EXISTS(ref) RETURNING`) : la ré-référence par un ingest concurrent est réévaluée dans le snapshot du DELETE, plus de suppression S3 sous un doc fraîchement ingéré. Value-object `ReingestResult`. +tests (409, purge/keep partagé, FAILED sur les 3 sites, delete race-safe). `1382 passed`, ruff clean. `config_version unique` (FAIBLE) reporté → vague migration.

- **2026-09-04 — ultrareview cloud (3 findings traités)** : (1) **[réel]** `QueryEmbedderProbe.classify` (chemin 424 du routeur search) contournait l'egress allowlist — trou parallèle dans mon fix SSRF ; la policy y est désormais construite (`from RUNTIME_CONFIG`) et passée à `probe_nodes` (host non listé → `blocked`, jamais sondé). +1 test. (2) **[réel]** `set_document_enabled` renvoyait un 200 faux-positif sur race de delete (j'avais jeté le retour `existed` en ajoutant le scope check) — re-check + 404 restauré. (3) **[nit]** allowlist MIME dupliquée front/back → commentaires croisés « keep in sync ». Tests verts.

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

- **2026-09-04 — V4 tranche 4 (validation overrides coût)** : `EstimateOverrides` acceptait des taux embed/ocr NÉGATIFS (valeurs de dict sans contrainte) et des assumptions INFINIES (`inf` passe `gt/ge`). Ajouté `NonNegativeRate` (ge=0) sur les valeurs embed/ocr + `allow_inf_nan=False` sur les 3 modèles. +6 tests (négatif/inf/nan rejetés, override valide accepté).

- **2026-09-04 — V5 tranche 1 (exhaustivité switch single-edge)** : `__check_single_path` n'appelait `__check_switch` que pour `count>1` → un seul edge WhenEquals sur un champ SWITCH_FIELDS clos sans défaut échappait au contrôle et tronquait silencieusement le groupe au run. Corrigé : `__check_switch` sur ≥1 edge WhenEquals (AMBIGUOUS reste sur >1 pour les autres kinds). +1 test single-edge. 17✓, pas de faux positif sur les tests multi-edge.

- **2026-09-04 — V7 tranche 1 (passe docs, agent dédié)** : 12 divergences doc↔code fermées, relues+vérifiées par moi (ColBERT purgé partout : 0 occurrence ; `metadata-architecture.md` archivé + banner, retiré du README ; rest-api.md +8 endpoints + erreurs typées 424/503/504 + range filters + score_kind ; python-sdk.md 9→13 ressources + jobs.list/JobPage + CREATE ; mcp.md list_audit + compte 55 vérifié ; configuration.md familles idempotency/audit + BGE_M3_MAX_LENGTH 2048 + FASTAPI_APP_VERSION ; CONTRIBUTING 5e projet paddle). Aucun code touché, diffs chirurgicaux (138+/36-).

- **2026-09-04 — V8 tranche 1 (proxy TLS cassé)** : `compose/overlays/proxy.yml` bindait `../../services/caddy/Caddyfile` — mais en add-on `-f` les chemins résolvent depuis le project dir (compose/), donc `../../` pointait HORS du repo → Docker montait un dossier vide, Caddy démarrait sans config (TLS mort dans toute invocation documentée). Corrigé en `../services/caddy/Caddyfile` (comme telemetry.yml) + en-tête. Validé : `docker compose config` résout `source: /…/docforge/services/caddy/Caddyfile` (présent).

- **2026-09-04 — V8 tranche 2 (sweep .claude)** : ghost-tree `docforge-rework`→`docforge` sur 40 fichiers .md (agents + mémoires + commands + rules) ; 3 skills cassées réparées (`/dev` → `compose/dev-cpu.yml`, `/test` ruff-only, `/phase-status`) ; `orchestrator.md` (mention historique + PIPELINE.md path) ; `hooks.py` rotation qui **supprime** désormais (KEEP_ROTATED=2) + purge one-off **209 Mo → 13 Mo**. `.claude` **sauvegardé** dans `/home/dev-center/backups/` (le dé-tracker reverserait le commit délibéré 922c627 « public-repo cleanup » — décision de versioning laissée à l'utilisateur) ; inner `.gitignore` corrigé (mcp-memory.json). NB : `.claude` est gitignored → ces fixes ne sont pas dans le commit (seul le tracker l'est). Reste `[~]` : vocab S0–S6 des rpi, seeding du knowledge-graph.

- **2026-09-04 — bge keep-warm (HAUTE)** : `_keep_warm` appelait `bge_models.encode_*`/`compute_rerank` en thread SANS acquérir `_embed_lock`/`_rerank_lock` → forward pass concurrent avec un vrai batch sur les modèles torch partagés (thread-unsafe). Nouvelles méthodes engine `touch_dense/sparse/rerank` (shape « direct mais verrouillé », comme `embed_all`) acquérant les mêmes locks ; `_keep_warm` recâblé. +2 tests (sérialisation vs batch réel, indépendance rerank). Agent `bge-server` dédié, relu+revérifié : 29✓, ruff+mypy clean. Le warmup one-time (avant `yield`, pas de concurrence) laissé intact à raison.

- **2026-09-04 — preflight + BlobNormalizer (2× HAUTE)** : agent `pipeline` dédié, relu + Part B finalisé/testé par moi. (A) `preflight()` ajouté à `ChunkerSemanticNode`, `FigureClassifyNode` (probe VLM, no-op sur `local`) et `BaseMetagenPrep` (endpoint défaut) → le sweep les sonde avant toute dépense ; commentaire config figure_classify corrigé. (B) `BlobNormalizer.normalize_reporting` détecte les nodes graph-level (edits `/edit`) que le heal ne round-trip pas ; le write boundary (`blob_helpers`) **refuse 422** avec message clair au lieu de perdre l'edit silencieusement — les blobs stock/stage healent sans drop (pas de faux positif). +2 tests. **Suite complète 1369 passed**.

- **2026-09-04 — parity-guards OpenAPI (HAUTE)** : agent `mcp` dédié, relu. Les 3 guards n'itéraient que `MODELS` → un nouvel endpoint/schéma mergeait sans méthode SDK (gate vert). Ajouté : (1) `test_every_snapshot_schema_is_tracked` — tout schéma OpenAPI ∈ MODELS ∪ SKIPPED (les 80+ non suivis triés : mappés à de vrais modèles SDK validés, ou SKIPPED avec raison — StrEnums/routes `include_in_schema=False`) ; (2) `route_map` + `test_every_snapshot_route_is_tracked`/`test_no_stale_tracked_routes` (couverture de routes bidirectionnelle, exemption `/jobs/{id}/stream`). 0 dette TODO. **542 tests** (+123), ruff clean. **→ les 4 HAUTE restantes sont fermées.**

- **2026-09-04 — V8 (dev builds retag prod images)** : un `--build` dev taguait les images aux noms GHCR de prod → un `up` prod ultérieur sur le même host pouvait tourner du code dev en silence. Deux correctifs complémentaires : (a) `dev.yml` tague `docforge-<svc>:dev` (les 5 services buildés — gagne via l'ordre include: en dev-cpu ; app/mcp aussi en dev-gpu) ; (b) `pull_policy: always` sur prod-cpu/prod-gpu (prod tire TOUJOURS de GHCR — couvre le résidu dev-gpu où l'image de gpu.yml gagne). Validé : dev-cpu→`:dev`, prod→GHCR+always, `config -q` OK sur les 4 scénarios.

## Avancement

> Compteurs recalculés + **tous les `[x]` vérifiés réellement intégrés sur `main` @ 0.14.8** (2026-09-04, vérif par signatures de code). Les 25 HAUTES sont **toutes** fermées et livrées (0.14.1→0.14.8).

| Vague | Total | Fait | En cours | Restant |
|---|---|---|---|---|
| V1 — Sécurité & authz | 30 | 29 | 0 | 1 |
| V2 — Fiabilité (jobs/stores/transferts) | 4 | 4 | 0 | 0 |
| V3 — Release/CI/dépendances | 1 | 1 | 0 | 0 |
| V4 — Search & coûts | 1 | 1 | 0 | 0 |
| V5 — Moteur & pipeline | 2 | 2 | 0 | 0 |
| V6 — Frontend | 0 | 0 | 0 | 0 |
| V7 — Documentation | 21 | 21 | 0 | 0 |
| V8 — Outillage (.claude/tests/infra/télémétrie) | 188 | 52 | 3 | 133 |
| **Total** | **247** | **110** | **3** | **134** |


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
- [x] **🟠 MOYENNE** · `security` — Log injection: user-controlled names/filenames logged raw with no sanitization, while the repo sanitizes correlation ids for exactly this reason  
  `src/docforge/app/backend/routers/documents/router.py:201`
- [x] **⚪ FAIBLE** · `security` — job.error / preflight / health `detail` persist raw provider exception strings — provider-echoed credentials and userinfo-bearing base_urls pass through unredacted  
  `src/docforge/worker/backend/libs/jobs/core.py:291`

### Sécurité & authz

- [x] **🔴 HAUTE** · `security` — .dcexport import lets a bundle overwrite arbitrary S3 objects (attacker-controlled s3_key)  
  `src/docforge/worker/backend/libs/collection_transfer/restore/importer.py:195`
- [x] **🔴 HAUTE** · `security` — MCP HTTP tools read arbitrary files from the MCP container (file_path tool inputs)  
  `src/mcp/libs/tools/documents.py:25`
- [x] **🟠 MOYENNE** · `security` — Collection import bypasses the CREATE capability and skips creator scope-grant  
  `src/docforge/app/backend/routers/transfers/router.py:85` _(aussi: backend-api)_
- [x] **🟠 MOYENNE** · `security` — Import resource exhaustion: decompression bomb + whole-corpus buffering in the worker  
  `src/docforge/worker/backend/libs/collection_transfer/bundle/archive.py:62`
- [x] **🟠 MOYENNE** · `security` — SSRF / internal-network oracle via per-collection provider base_url (unmitigated, unacknowledged)  
  `src/docforge/shared/libs/pipelines/nodes/openai_compat/preflight.py:92`
- [x] **⚪ FAIBLE** · `bug` — 500-instead-of-4xx and scope-gate edge cases (grouped)  
  `src/docforge/app/backend/routers/auth/whoami.py:40`
- [x] **⚪ FAIBLE** · `design` — Hardening smells (grouped): blob/HTML response headers, MCP client cache, redaction export list  
  `src/docforge/app/backend/routers/blobs/router.py:45`
- [x] **⚪ FAIBLE** · `divergence-doc` — Imported pipeline/search blobs are stored without the fail-fast validation every other write path enforces  
  `src/docforge/worker/backend/libs/collection_transfer/restore/importer.py:147`
- [x] **⚪ FAIBLE** · `security` — Unauthenticated requests bypass the rate limiter; XFF trusted by default  
  `src/docforge/app/backend/app.py:86`

### Dépendances & licences

- [x] **🟠 MOYENNE** · `security` — GPU images ship torch 2.6.0 (cu124 index is EOL) while CPU ships 2.12.1/2.13.0; CPU worker torch also below the PYSEC-2025-194 fix  
  `src/docforge/uv.lock:4661`
- [x] **🟠 MOYENNE** · `security` — Stale transitive pins with published security fixes across the docforge and mcp locks  
  `src/docforge/uv.lock:99`
- [x] **🟠 MOYENNE** · `security` — pypdf 6.14.2 carries 6 known advisories and parses untrusted uploads at intake  
  `src/docforge/uv.lock:3528`
- [x] **⚪ FAIBLE** · `security` — mcp 1.28.0 in the MCP server lock has a known advisory fixed one patch away (1.28.1)  
  `src/mcp/uv.lock:514`
- [x] **⚪ FAIBLE** · `security` — transformers<5 pins freeze both ML services on a line whose security fixes are 5.x-only  
  `src/docforge/pyproject.toml:95`

### Infra & compose

- [x] **🟠 MOYENNE** · `consistency` — Fresh-clone credential mismatch: base.yml's default POSTGRES_DSN (docforge:docforge) does not match the shipped postgres.env.example (change_me)  
  `compose/base.yml:43`
- [x] **🟠 MOYENNE** · `security` — Unauthenticated Gotenberg published on host port 10045 in every scenario including prod, contradicting docs/configuration.md's exposure claim  
  `compose/base.yml:272`

### Infra .claude

- [x] **🟠 MOYENNE** · `security` — hook logs retain secrets in plaintext with unbounded retention (full tool_input/tool_response of every call)  
  `.claude/hooks/hooks.py:117` _(local .claude, gitignored — hors release ; rétention déjà bornée V8 tranche 2, redaction ajoutée 2026-09-05)_
- [ ] **⚪ FAIBLE** · `security` — settings.json runs every session in bypassPermissions with a blanket allow list  
  `.claude/settings.json:9`

### Serveurs modèles

- [x] **🟠 MOYENNE** · `security` — paddle_server buffers unbounded request bodies — no size cap on /ocr or /layout-parsing  
  `src/paddle_server/backend/routers/ocr/router.py:40`

### CI & release

- [x] **⚪ FAIBLE** · `security` — Workflow hardening gaps: no permissions on ci/gate, gate inherits packages:write during releases, mutable action refs in the OIDC publish job  
  `.github/workflows/ci.yml:20`

### Middlewares HTTP

- [x] **⚪ FAIBLE** · `security` — X-Forwarded-For trusted by default (leftmost hop) while the default deployment has no proxy — forgeable audit client_ip out-of-box, rate-limit keying bypass when enabled with auth off  
  `src/docforge/app/config/runtime_config.py:112`

### Search & retrieval

- [x] **⚪ FAIBLE** · `security` — Search-side SSRF parity: per-collection base_urls + probe endpoints form an internal-network reachability oracle  
  `src/docforge/app/backend/routers/search/helpers.py:339`

### Télémétrie

- [x] **⚪ FAIBLE** · `security` — Grouped low-severity security notes on the telemetry overlay  
  `compose/overlays/telemetry.yml:84`


## V2 — Fiabilité: jobs, stores, transferts  (4)

### Données Postgres·Qdrant·S3

- [x] **🔴 HAUTE** · `bug` — Import staging bundles leak in S3 forever — GC sweeps exports only  
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

- [x] **🔴 HAUTE** · `design` — BlobNormalizer heal silently discards graph-level customisations from the documented /edit surface  
  `src/docforge/shared/libs/pipelines/ingest/stages/normalizer.py:104`

### Pipeline ingest

- [x] **🔴 HAUTE** · `bug` — Preflight coverage gaps: figure_classify (VLM), semantic chunker, metagen default endpoint — with a config comment falsely claiming preflight coverage  
  `src/docforge/shared/libs/pipelines/ingest/nodes/enrich/figure_classify/core.py:56`


## V7 — Documentation  (21)

### Documentation

- [x] **🔴 HAUTE** · `divergence-doc` — metadata-architecture.md is a legacy-engine reference presented as current — schema, stages and hashes all wrong  
  `docs/metadata-architecture.md:1`
- [x] **🔴 HAUTE** · `divergence-doc` — rest-api.md documents removed ColBERT params use_late_interaction / rescore_pool_size that now 422  
  `docs/rest-api.md:478` _(aussi: claude-infra, docs-freshness, search-runtime)_
- [x] **🟠 MOYENNE** · `divergence-doc` — PIPELINE.md (the self-declared living reference) omits the deliver family / bundle terminal entirely  
  `src/docforge/PIPELINE.md:61`
- [x] **🟠 MOYENNE** · `divergence-doc` — configuration.md misses the whole idempotency + audit env-var families  
  `docs/configuration.md:24`
- [x] **🟠 MOYENNE** · `divergence-doc` — configuration.md: BGE_M3_MAX_LENGTH default wrong (doc 8192, code 2048); several bge/paddle vars undocumented  
  `docs/configuration.md:181`
- [x] **🟠 MOYENNE** · `divergence-doc` — configuration.md: FASTAPI_APP_VERSION described as required with default 0.2.0 — actually optional, defaults from DOCFORGE_TAG  
  `docs/configuration.md:41`
- [x] **🟠 MOYENNE** · `divergence-doc` — mcp.md tool catalogue misses list_audit; tool totals stale (54 and 38 vs actual 55)  
  `docs/mcp.md:168` _(aussi: sdk-mcp)_
- [x] **🟠 MOYENNE** · `divergence-doc` — python-sdk.md: jobs.list() return type wrong — returns JobPage, not list[JobStatus]  
  `docs/python-sdk.md:338`
- [x] **🟠 MOYENNE** · `divergence-doc` — rest-api.md filters contract under-documented: range predicates (gte/gt/lte/lt) exist but are absent  
  `docs/rest-api.md:476`
- [x] **🟠 MOYENNE** · `divergence-doc` — rest-api.md misses 8 live endpoints: collection health/storage/reingest, job cancel, and all 4 transfers routes  
  `docs/rest-api.md:41`
- [x] **⚪ FAIBLE** · `divergence-doc` — CONTRIBUTING.md: 'monorepo of four standalone uv projects' — paddle_server is a fifth, CI-gated package  
  `CONTRIBUTING.md:3`
- [x] **⚪ FAIBLE** · `divergence-doc` — Ground-truth docs stale: CLAUDE.md family/node lists miss structgen+deliver; tests list incomplete; rules/architecture.md says preflight 'reste à ajouter' though shipped  
  `CLAUDE.md:1`
- [x] **⚪ FAIBLE** · `divergence-doc` — PIPELINE.md stale statuses: block-id remap marked pending though shipped; item-index-in-progress-events caveat outdated; tree misses vlm_entry/parser kinds; nodes list misses structgen  
  `src/docforge/PIPELINE.md:485`
- [x] **⚪ FAIBLE** · `divergence-doc` — README.md workflows note omits release-images.yml  
  `README.md:169`
- [x] **⚪ FAIBLE** · `divergence-doc` — Response payloads richer than documented: SearchHit, JobStatus and jobs list pagination under-described in rest-api.md  
  `docs/rest-api.md:493`
- [x] **⚪ FAIBLE** · `divergence-doc` — architecture.md grouped staleness: SDK resource list, frontend gate steps, self-referential rename note  
  `docs/architecture.md:75`
- [x] **⚪ FAIBLE** · `divergence-doc` — brand.md muted/pending hex #8a8378 diverges from the implemented tokens  
  `docs/brand.md:28`
- [x] **⚪ FAIBLE** · `divergence-doc` — deployment-resources.md still flags getting-started.md's '~10 GB / 8 GB' claim as needing a fix that already landed  
  `docs/deployment-resources.md:39`
- [x] **⚪ FAIBLE** · `consistency` — getting-started.md port-range claims inconsistent: '10040–10048' vs published 10049 and troubleshooting's 10040–10052  
  `docs/getting-started.md:19`
- [x] **⚪ FAIBLE** · `divergence-doc` — getting-started.md: field-type list names 6 of 11 types  
  `docs/getting-started.md:182`
- [x] **⚪ FAIBLE** · `consistency` — python-sdk.md auth section drops the CREATE capability from the KeyPermissions bullet  
  `docs/python-sdk.md:387`


## V8 — Outillage: .claude, tests, infra, télémétrie  (188)

### Backend API

- [x] **🔴 HAUTE** · `bug` — SSE job stream never closes for a CANCELLED job — polls the DB forever  
  `src/docforge/app/backend/routers/jobs/stream.py:19`
- [x] **🟠 MOYENNE** · `bug` — Check-then-insert races surface as 500: duplicate concurrent upload and duplicate collection name hit unique constraints uncaught  
  `src/docforge/app/backend/routers/documents/router.py:125`
- [ ] **🟠 MOYENNE** · `perf` — Unbounded whole-collection reads: estimate default scope, explorer document list, and bulk delete have no cap  
  `src/docforge/app/backend/libs/estimate/service.py:130` _(aussi: money-math)_
- [ ] **🟠 MOYENNE** · `design` — update_collection applies contract, schema, blob and override writes as separate commits — a mid-sequence failure leaves a half-applied PATCH  
  `src/docforge/app/backend/routers/collections/router.py:348`
- [x] **⚪ FAIBLE** · `bug` — GET /auth/whoami 500s on a malformed permissions blob instead of degrading like the authz gate  
  `src/docforge/app/backend/routers/auth/whoami.py:40`
- [ ] **⚪ FAIBLE** · `consistency` — Grouped minor issues: unbounded bulk-chunk patch, transfer info disclosed before scope check, catch-all ValueError→422, READ-triggered export side effects, whole-blob buffering, duplicated lifespan step number  
  `src/docforge/app/backend/routers/explorer/models.py:134`
- [ ] **⚪ FAIBLE** · `divergence-doc` — RUNTIME_CONFIG idempotency comment claims key create/rotate are eligible endpoints — eligibility.py deliberately excludes them  
  `src/docforge/app/config/runtime_config.py:118`

### Infra & compose

- [x] **🔴 HAUTE** · `bug` — proxy.yml Caddyfile bind mount resolves outside the repo — TLS add-on broken in every documented invocation  
  `compose/overlays/proxy.yml:48` _(aussi: telemetry-configs)_
- [x] **🟠 MOYENNE** · `design` — Dev builds retag the GHCR prod image names — a later prod `up` on the same host silently runs the dev-built image  
  `compose/overlays/dev.yml:30`
- [x] **🟠 MOYENNE** · `consistency` — Grafana admin password mechanism drift: Makefile exports a variable nothing consumes; root .env.example documents the retired mechanism  
  `Makefile:83`
- [x] **🟠 MOYENNE** · `perf` — No .dockerignore for the src/docforge build context — 386 MB .venv, host node_modules stub and dist enter every app/worker build  
  `src/.dockerignore:1`
- [x] **🟠 MOYENNE** · `divergence-doc` — compose/README.md documents a nonexistent compose/telemetry/ dir and the wrong overlay path rule  
  `compose/README.md:17` _(aussi: telemetry-configs)_
- [x] **🟠 MOYENNE** · `divergence-doc` — dev.yml/gpu.yml headers document a manual -f invocation whose paths resolve outside the repo, plus a 'last-include wins' claim that contradicts the verified first-wins rule  
  `compose/overlays/dev.yml:4`
- [x] **🟠 MOYENNE** · `design` — docforge_app has no healthcheck — the one service everything else fronts can wedge silently  
  `compose/base.yml:23`
- [x] **⚪ FAIBLE** · `design` — Robustness gaps: missing healthchecks/limits on secondary services, app's incomplete depends_on, S3 gateway not probed (grouped)  
  `compose/overlays/telemetry.yml:74`
- [x] **⚪ FAIBLE** · `divergence-doc` — Stale comments across compose/CI/Dockerfiles (grouped)  
  `compose/base.yml:15`

### Infra .claude

- [~] **🔴 HAUTE** · `design` — .claude/ is gitignored and untracked — the entire agent infrastructure (750KB of memory, 10 agents, rules, hooks) exists in a single unversioned copy that was already silently lost once  
  `.gitignore:58`
- [x] **🔴 HAUTE** · `bug` — /dev, /test and /phase-status skills are hard-broken: nonexistent compose files, dirs and service names  
  `.claude/commands/dev.md:25`
- [x] **🔴 HAUTE** · `divergence-doc` — All 10 agent definitions target the ghost tree src/docforge-rework/ and call the live tree 'frozen legacy'  
  `.claude/agents/pipeline.md:29`
- [x] **🔴 HAUTE** · `bug` — hooks.py log rotation never deletes: docstring promises 'only one rotated copy', code keeps all — 199MB and growing unbounded  
  `.claude/hooks/hooks.py:88`
- [x] **🟠 MOYENNE** · `divergence-doc` — Agent-memory rot: 26 files still teach rework-era paths, and 4+ memories document the ColBERT feature that no longer exists  
  `.claude/agent-memory/backend/colbert-named-vector.md:1`
- [~] **🟠 MOYENNE** · `divergence-doc` — The 3 rpi skill commands still describe the deleted S0→S6 static engine (engine.py DAG, provider Protocols, S2_ENRICH_ENABLED, phase table)  
  `.claude/commands/rpi/research.md:22`
- [~] **🟠 MOYENNE** · `dead-code` — The knowledge graph orchestrator.md builds its whole long-term-memory protocol on does not exist — wrong path in the doc, and no file at the configured path either  
  `.claude/rules/orchestrator.md:100`
- [ ] **🟠 MOYENNE** · `divergence-doc` — architecture.md claims per-node preflight() 'reste à ajouter' — it shipped, is on by default, and is CLAUDE.md invariant 4  
  `.claude/rules/architecture.md:76`
- [x] **🟠 MOYENNE** · `consistency` — orchestrator.md contradicts itself and the tree: auto-improvement table routes pipeline updates to src/docforge-rework/PIPELINE.md  
  `.claude/rules/orchestrator.md:76`
- [ ] **⚪ FAIBLE** · `consistency` — Grouped low-severity smells across .claude/: decorative paths filter, deprecated utcnow, stale lock/pycache, misnamed memory file  
  `.claude/rules/brand.md:3`
- [ ] **⚪ FAIBLE** · `dead-code` — scripts/update_imports.py is a dead one-off targeting the deleted legacy layout, still tracked with no caller  
  `scripts/update_imports.py:15`

### SDK & MCP

- [x] **🔴 HAUTE** · `test-gap` — OpenAPI parity guards silently pass on additive drift — no completeness check over schemas or routes  
  `src/docforge_sdk/tests/check_schema_drift.py:89`
- [x] **🟠 MOYENNE** · `test-gap` — Async/sync lockstep guard and unit tests skip the three newest SDK resources (audit, corpus, snippets)  
  `src/docforge_sdk/tests/unit/test_resource_parity.py:25`
- [x] **🟠 MOYENNE** · `divergence-doc` — MCP tool surface is not the promised 'full REST surface': collection health probe and collection-level bulk reingest have no tool  
  `src/mcp/libs/tools/collections.py:24`
- [x] **🟠 MOYENNE** · `design` — MCP tools swallow the API error body — a 4xx surfaces to the LLM as an opaque status code  
  `src/mcp/libs/tools/search.py:50`
- [x] **🟠 MOYENNE** · `divergence-doc` — docs/python-sdk.md is four resources behind the SDK (transfers, corpus, snippets, audit all undocumented)  
  `docs/python-sdk.md:108` _(aussi: docs-freshness)_
- [x] **⚪ FAIBLE** · `consistency` — Minor SDK/MCP inconsistencies (grouped): client docstrings omit corpus, divergent get_pipeline_design default, stale 0.1.1 dist artifacts  
  `src/docforge_sdk/docforge_sdk/client.py:31`
- [ ] **⚪ FAIBLE** · `design` — ScopedSdkProvider eviction is FIFO-not-LRU and closes evicted clients via an unreferenced fire-and-forget task  
  `src/mcp/libs/scoped_sdk.py:127`

### Serveurs modèles

- [x] **🔴 HAUTE** · `bug` — bge keep-warm task bypasses the engine locks and races real forward passes on the same model instances  
  `src/bge_server/backend/lifespan.py:49`
- [x] **🟠 MOYENNE** · `design` — /embed_all has no back-pressure: bypasses the bounded queues, can never return 503  
  `src/bge_server/libs/batching/engine.py:385`
- [ ] **🟠 MOYENNE** · `design` — Bad image bytes on /ocr surface as HTTP 500 with raw exception text — client errors indistinguishable from server faults  
  `src/paddle_server/backend/routers/ocr/router.py:47`
- [ ] **🟠 MOYENNE** · `dead-code` — PADDLE_USE_DOC_UNWARPING env var is dead — its comment promises operators an override that silently does nothing  
  `src/paddle_server/config_loader.py:94`
- [x] **🟠 MOYENNE** · `consistency` — Thread-budget derivation assumes 1 concurrent model call while the two-lock engine allows 2 — engine docstring and service code contradict each other  
  `src/bge_server/libs/bge_models/service.py:87`
- [ ] **🟠 MOYENNE** · `divergence-doc` — no-AVX SIGILL constraint is documented in docs/ but completely unguarded in paddle_server — container reports healthy, then dies on first inference  
  `src/paddle_server/backend/routers/health/router.py:46`
- [x] **⚪ FAIBLE** · `consistency` — /rerank claims to mirror TEI but returns input order where TEI returns score-descending order  
  `src/bge_server/backend/routers/inference/router.py:220`
- [x] **⚪ FAIBLE** · `consistency` — bge_server stale doc/comment cluster: retired single-lock design, wrong worker count, phantom constructor args, dead port reference  
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
- [x] **⚪ FAIBLE** · `test-gap` — Lockstep version test and set_version.sh cover only 3 of 6 version declarations — frontend package.json, bge_server, paddle_server are outside the loop  
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
- [x] **⚪ FAIBLE** · `bug` — Override validation gaps: negative embed/OCR rates and infinite assumption values are accepted  
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
- [x] **🟠 MOYENNE** · `perf` — Disabled-document exclusion list is unbounded and rides every prefetch branch of every search  
  `src/docforge/shared/libs/services/db/facades/search_facade.py:86`
- [x] **🟠 MOYENNE** · `bug` — Orphan-blob purge races a concurrent ingest sharing the same content hash  
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

- [x] **🟠 MOYENNE** · `design` — Export is not snapshot-consistent: blob hashes and points are read from the live DB after the document pass, so a concurrent reingest/delete produces a bundle that fails at import or silently loses data  
  `src/docforge/worker/backend/libs/collection_transfer/export/exporter.py:225`
- [x] **🟠 MOYENNE** · `bug` — Hard worker kill mid-import leaves a permanent half-imported collection and a forever-RUNNING transfer row — no reaper covers collection_transfer  
  `src/docforge/worker/backend/libs/jobs/transfer.py:136`
- [x] **🟠 MOYENNE** · `perf` — Import buffers every blob's bytes in memory at once — up to IMPORT_MAX_BUNDLE_BYTES (5 GiB default) resident — while export streams one blob at a time  
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

- [x] **🟠 MOYENNE** · `bug` — A chunks-fetch error blanks the entire Layout tab, contradicting its own degrade-without-chunks design  
  `src/docforge/app/frontend/src/features/explorer/DocumentPage.tsx:133` _(aussi: new-batch)_
- [x] **🟠 MOYENNE** · `divergence-doc` — Brand rule "Nothing below 11px" violated: hardcoded fontSize 9 in the new Layout components  
  `src/docforge/app/frontend/src/features/explorer/layout/ChunkProvenance.tsx:55` _(aussi: new-batch)_
- [x] **🟠 MOYENNE** · `bug` — Job-detail ETA never subtracts completed stages (job-status set tested against event statuses)  
  `src/docforge/app/frontend/src/features/monitoring/state/useJobDetail.ts:191`
- [x] **🟠 MOYENNE** · `perf` — Layout tab loads and renders the whole document eagerly — N simultaneous page-image fetches, refetched on every tab switch, plus unmemoized per-render recomputation  
  `src/docforge/app/frontend/src/features/explorer/layout/LayoutTab.tsx:91` _(aussi: new-batch)_
- [ ] **🟠 MOYENNE** · `test-gap` — No tests anywhere in the batch: pure grouping/segmentation helpers, LayoutTab smoke, /provenance endpoint, startup reclaim and the CancelledError terminal path are all untested  
  `src/docforge/app/frontend/src/features/explorer/layout/chunkGrouping.ts:47` _(aussi: frontend, tests-audit)_
- [x] **🟠 MOYENNE** · `bug` — Per-document tab caches never reset when documentId changes without a remount — wrong document's data shown  
  `src/docforge/app/frontend/src/features/explorer/state/useDocumentTabs.ts:59`
- [ ] **🟠 MOYENNE** · `bug` — Provenance returns the latest job even when it failed, so it can describe a run that did NOT produce the displayed IR  
  `src/docforge/shared/libs/services/db/postgresql/apis/job_api.py:67` _(aussi: backend-api)_
- [x] **🟠 MOYENNE** · `perf` — Search Lab fetches the entire unpaginated document list just to learn "has documents"  
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
- [x] **🟠 MOYENNE** · `bug` — Switch exhaustiveness check skipped when a node has only one WhenEquals edge  
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
- [x] **⚪ FAIBLE** · `test-gap` — No test covers single-edge switch exhaustiveness or SetAfter on a convergence node  
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
- [x] **🟠 MOYENNE** · `divergence-doc` — Typed search failure modes (424/503/504, score_kind, range filters) undocumented in rest-api.md  
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

- [x] **🟠 MOYENNE** · `consistency` — Enqueue-failure handling inconsistent: upload and single reingest can leave a forever-PENDING job no reaper covers  
  `src/docforge/app/backend/routers/documents/router.py:200`
- [ ] **🟠 MOYENNE** · `dead-code` — Enrichment attempt trace and entity mentions are never persisted — the tables, read APIs and export path are write-dead on ingest  
  `src/docforge/worker/backend/libs/jobs/core.py:188`
- [x] **🟠 MOYENNE** · `bug` — No guard against two concurrent runs of the same document — interleaved Qdrant delete/upsert can strand orphan points  
  `src/docforge/app/backend/routers/documents/router.py:260`
- [x] **🟠 MOYENNE** · `perf` — Re-ingest leaks superseded blobs: save() replaces rows but never orphan-purges the previous run's S3 objects  
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
