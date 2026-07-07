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
`scored`, `switch_fields`, `error_policy`. La persistance se fait **aux bords, dans le worker** (façade
`Database`), jamais dans un node.

## Les familles (palette UI)

Dédiées à une étape : `intake · converter · parser · render · enrich · chunker · contextualize · metagen`.
Génériques réutilisables : `embed · ocr · vlm · llm` (+ la factory `openai_compat`).
**Convention kinds** : jamais de redondance famille+kind (`(ocr, mistral)`, pas `mistral_ocr` ;
`(contextualize, llm)`, pas `llm_context`). Un nouveau provider = un kind de plus dans sa famille,
interchangeable dans l'UI — rien à changer au moteur.

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

## La validation (avant toute dépense — `GraphValidator`)

Entrée unique · pas de cycle · pas de fan-out ambigu · bindings amont présents + types compatibles ·
`ScoreBelow` ⇒ producteur `scored` · unicité des nodes single-use. Un blob cassé revient en **donnée**
(`valid=false` + `issues`, `build_error` si inconstruisible) — jamais en erreur HTTP.

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
