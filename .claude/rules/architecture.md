---
paths:
  - "src/docforge-rework/**"
---

# DocForge (v2) — Architecture du moteur graphe

> Cheat-sheet pour **éditer la pipeline**. Le récit complet des 7 étapes (nodes, artefacts, décisions,
> diagrammes) vit dans `src/docforge-rework/PIPELINE.md` — tenu à jour à chaque évolution. Ici : les
> invariants du moteur qu'un agent doit respecter quand il ajoute un node, une famille ou une arête.

## Le contrat d'un node

Un node est **pur** : `Config` (une `NodeConfig`, `extra="forbid"`) + `Consomme → Produit`, **zéro I/O
DB/S3**. Il déclare via `describe()` : ses slots typés IN/OUT (classe d'`Artifact` ou `list[Artifact]`,
chacun **décrit** — un slot sans description est rejeté par test), sa `family`/`kind`, `UNIQUE_IN_GRAPH`,
`scored`, `switch_fields`, `error_policy`, **`selectable`** (défaut `True` ; les nodes internes de câblage —
prep/apply/skip/keep_raw — le mettent `False` : cachés du picker de méthodes de la palette via l'unique
chokepoint `NodeRegistry.catalog`, mais toujours dans le registre — `kinds()`/`get()`/`describe()` les
atteignent). La persistance se fait **aux bords, dans le worker** (façade `Database`), jamais dans un node.

## Les familles (palette UI)

Dédiées à une étape : `intake · converter · parser · render · enrich · chunker · contextualize · metagen`.
Génériques réutilisables : `embed · ocr · vlm · llm · structgen` (+ la factory `openai_compat`).
**Convention kinds** : jamais de redondance famille+kind (`(ocr, mistral)`, pas `mistral_ocr` ;
`(contextualize, llm)`, pas `llm_context`). Un nouveau provider = un kind de plus dans sa famille,
interchangeable dans l'UI — rien à changer au moteur.

## Les chaînes de fallback (tout appel d'interface, P1–P6 terminé)

Un node d'action qui appelle une interface standard (`parser`/`ocr`/`vlm`/`embed`/`llm`/`structgen`) délègue à
une **chaîne = providers en nodes + transitions de fallback dans le graphe** — `ScoreBelow(seuil)` si la famille
est `scored` (auto-dérivé : `Produces` sous-classe `ScoredOutput`), sinon `OnFailure` — convergeant en `FromFirst`
(meilleur d'abord). Motif uniforme `prep → chaîne → finalize` (métagen/contextualize : `prep → ForEach(chaîne
[+ terminal fail-soft]) → apply`). **Un provider unique = une chaîne à 1 étape** (byte-identique à un node seul).
Socle : `ChainFragmentBuilder` (build/), `ChainRules.resolve()` + `ChainWalker` (stages/, lecture inverse
famille-paramétrée). Éditée par `set_chain` (stage à slot) ou, pour le stack contextualize, la `ChainSpec` portée
par chaque `StackMethod` via `set_stack`.

## La mécanique du graphe (`shared_libs.pipelines.base`)

- **Transitions** (contrôle) : `OnSuccess` · `OnFailure` · `ScoreBelow(seuil)` · `WhenEquals(field, val)` ·
  `Always`. Priorité de sélection : `ScoreBelow > WhenEquals > OnSuccess/OnFailure > Always`.
- **Bindings** (données) : `FromRunInput(field)` · `FromNode(node_id, field)` (n'importe quel amont) ·
  `FromGroupInput(field)` · `FromFirst([candidats])` (jointure de convergence après un embranchement).
- **`ForEach`** : sous-graphe par item — `over` (un `list[T]` amont) · `item_field` · `max_concurrency` ·
  tous les terminaux du corps produisent le MÊME `Artifact` à slot unique → sortie `items: list[T]`
  (ordre préservé, 1 record d'exécution par item, échec d'item = échec bruyant).
- **`UNIQUE_IN_GRAPH=True`** : une 2e instance du kind est une erreur de câblage (rejet au build
  `duplicate_unique_node`). `False` quand la répétition est légitime (providers en escalade, terminaux
  multi-branches).

## La validation (structurelle, avant toute dépense — `GraphValidator`)

Entrée unique · pas de cycle · pas de fan-out ambigu · bindings amont présents + types compatibles ·
`ScoreBelow` ⇒ producteur `scored` · unicité des nodes single-use. Un blob cassé revient en **donnée**
(`valid=false` + `issues`, `build_error` si inconstruisible) — jamais en erreur HTTP.

> **Portée honnête** : la validation est **structurelle** (topologie + forme de config `extra="forbid"`).
> Elle ne teste **PAS la connectivité** : un `base_url`/`api_key` faux ou injoignable construit proprement
> et n'échoue qu'au **run** (surfacé par `job.error` qui nomme le node fautif). Un `preflight()` optionnel
> par node — joignabilité/creds après `bind`, avant la 1re dépense — reste à ajouter.

## Deux pipeline kinds sur le MÊME moteur (`PipelineRegistry`)

Le moteur ne code en dur **aucune** pipeline. `pipeline_registry.PipelineRegistry` mappe `key → façade`
(`ingest` · `search`) ; le routeur `pipelines/` l'itère (`/pipelines/{key}`). **Ingestion** tourne async
dans le worker ; **search** tourne INLINE dans la requête API (sub-seconde, zéro arq) via un `SearchRunner`
app-side (`build → validate → bind → FlowEngine.execute → assert SearchResult`). Familles search dédiées :
`query · encode · retrieve · fuse · rerank · postprocess` (+ `deliver`). Détail : `docs/rpi/search-pipeline/`.

**Deux blobs par collection, symétriques** : `collection.pipeline` (blob ingest, run au worker) et
`collection.search` (blob search, run inline par `SearchService.__resolve_blob` ; `{}` = défaut stock).
Chacun validé **au write** en fail-fast : `PipelineBlobValidator` (structurel) pour ingest ; pour search,
`SearchBlobValidator` ajoute le **contrat terminal** (un exit doit produire un `SearchResult`, via
`GraphTopology.exits` + le `Produces` du node) — un graphe non-search est rejeté 422 à l'écriture, jamais
un 500 au run. La famille `deliver` étant partagée, chaque façade **scope sa palette** par `FAMILY_KINDS`
(ingest→`bundle`, search→`hits`).

**Le seam `bind()` est vivant** (n'était que du scaffolding mort). Un node peut recevoir une **capacité
read-only** (`self._capabilities`) — le `CollectionReadPort` de search est injecté ainsi APRÈS `build`,
AVANT `execute` (le moteur n'appelle **jamais** `bind()` — c'est au runner de walker `group.children`, **y
compris les corps de `ForEach`**). Un node reste **pur** : il peut LIRE (provider ou store read-only via
capacité injectée) mais n'ÉCRIT jamais. Un accès write reste une façade au bord worker.

**Trois surfaces orthogonales de recherche des métadonnées** (flags par champ, pilotent tout) :
`filterable` (→ payload Qdrant, filtre exact/any-of), `semantic` (→ vecteur nommé `meta_<slug>_dense`),
`lexical` (→ vecteur sparse `meta_<slug>_bm25`). Un champ **document-scope** étant partagé par tous ses
chunks, ses valeurs sont **dénormalisées sur chaque point** : `FilterSyncFacade` pousse le scalaire
filtrable (payload) et `MetaVectorSyncFacade` pousse les vecteurs semantic/lexical (`update_vectors`,
zéro réembedding du contenu) — les deux en **hook best-effort après `index()`** + un **job de backfill**
(chemin de réparation ; ne JAMAIS faire échouer une ingestion déjà persistée). Côté lecture, un
`SearchTarget` (`{field, semantic, lexical}`) choisit QUELS vecteurs nommés interroger (content et/ou
metadata, jusqu'au metadata-only) ; le `TargetVectorResolver` (app-side, à côté du read port) est le
**seul** endroit qui connaît les noms de vecteurs — aucun node search n'en apprend un. Fail-fast 422 au
routeur si une cible nomme un vecteur non indexé.

## Les 3 racines et l'import model

| Racine | Namespace | Rôle |
|---|---|---|
| `shared/libs/` | `shared_libs.*` | moteur pur (`pipelines/`), `public_models/ir`, façade `services/db` |
| `app/` | `backend.*` | FastAPI (routers pipelines/collections/documents/explorer/jobs/blobs) + frontend |
| `worker/` | `backend.libs.*` | arq : `runner/` (exécute la pipeline pure) · `persistence/` (translator IR→DB) · `jobs/` |

`config` (donc `RUNTIME_CONFIG`) **s'importe en premier** dans chaque entrypoint : il enregistre l'alias
`shared_libs` et met `backend/libs` sur le `sys.path` (`RuntimePathHelpers`). En test,
`tests/conftest.py` installe l'alias **une seule fois** — le `NodeRegistry` est un état **global process**.

## La surface de design (API)

`GET /api/v1/pipelines` (découverte) → `GET …/ingest` (palette maigre + blob par défaut validé) →
`POST …/ingest/stages/{view,apply}` (le stage-rail produit). Surface avancée headless (`?full=true`,
`/inspect`, `/edit`) conservée et testée, sans consommateur UI aujourd'hui. **Règle** : tout champ
(config, slot, artefact) sans `description` est non conforme (verrouillé par test).

## Où poser quoi

- Un provider générique (ocr/vlm/llm/embed) → `shared/libs/pipelines/nodes/<family>/`.
- Un node d'étape d'ingestion → `shared/libs/pipelines/ingest/nodes/<stage>/`.
- Un accès DB/S3/Qdrant → une **façade** dans `shared/libs/services/db/facades/`, appelée par le worker,
  jamais depuis un node ou un router directement.
