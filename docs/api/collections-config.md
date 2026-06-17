# Collections — Config — API Reference

Sous-ressource de la collection. Préfixe commun : `/api/v1/collections/{collection_id}/config`

La config d'une collection est le **contrat complet** qui régit l'ingestion et la recherche :
- le contrat d'admission (formats, taille, localité, politique champs inconnus)
- le schéma de métadonnées (champs système + champs métier)
- le pipeline ML (parse → enrich → chunk → embed) avec ses providers

Les cinq endpoints de cette section partagent le même helper `_load(collection_id)` : toute collection inconnue retourne **404** avant d'aller plus loin.

---

## GET /config/state

Retourne la configuration complète et actuelle de la collection.

### Comportement

Charge la collection depuis Postgres, construit le document de config canonique via `ConfigDocument.from_collection()`, puis sérialise le pipeline via `PipelineConfig.redacted_dict()` avant de l'inclure dans la réponse.

> **Redaction** — Tout param de provider dont la clé contient un segment `key`, `apikey`, `token`, `secret`, `password`, `credential` ou `auth` est remplacé par `"•••"` dans la réponse. Les credentials ne transitent jamais en clair vers le client.

### Réponse

**200 OK**

```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "name": "Rapports annuels",
  "pipeline_version": "v3",
  "needs_reindex": false,
  "supported_formats": ["pdf", "docx"],
  "max_file_size_bytes": 104857600,
  "max_pages": null,
  "locality_policy": "external_allowed",
  "embedding_model": "BAAI/bge-m3",
  "unknown_field_policy": "reject",
  "pipeline": {
    "parse":   { "provider": { "id": "docling", "params": {} } },
    "enrich":  { "enabled": false, "chart_to_data": false, "max_budget_usd": 0.0,
                 "classifier": { "id": "layout_labels", "params": {} },
                 "ocr_chain": [], "vlm": null },
    "chunk":   { "split_method": { "id": "token_budget",
                                   "params": { "max_tokens": 512, "overlap_blocks": 0 } },
                 "hierarchical": false, "cross_references": true,
                 "atomic": { "tables": true, "figures": true, "formulas": true,
                             "keep_caption_with_figure": true },
                 "contextualize": true, "reinject_breadcrumb": true,
                 "merge_short_sections": true, "heading_rules": [...] },
    "embed":   { "provider": { "id": "tei_bge_m3",
                               "params": { "base_url": "http://tei:8080", "model": "BAAI/bge-m3" } } }
  },
  "metadata_fields": [
    { "field_name": "filename", "field_type": "string", "required": false,
      "filterable": true, "lexical": true, "semantic": false,
      "weight_lexical": 1.0, "weight_semantic": 1.0, "enum_values": null, "is_system": true },
    ...
  ]
}
```

**Champs de la réponse :**

| Champ | Mutabilité | Description |
|---|---|---|
| `id` | immutable | UUID de la collection |
| `name` | immutable | Nom humain |
| `pipeline_version` | auto (état) | Incrémenté à chaque PATCH qui touche le pipeline ou l'embedding model |
| `needs_reindex` | auto (état) | `true` si le changement d'embedding model rend les vecteurs obsolètes |
| `supported_formats` | éditable | Extensions acceptées à l'ingestion |
| `max_file_size_bytes` | éditable | Plafond de taille |
| `max_pages` | éditable | Plafond de pages (`null` = illimité) |
| `locality_policy` | éditable | `on_premise_only` \| `external_allowed` |
| `embedding_model` | éditable | Modèle d'embedding (changer → `needs_reindex=true`) |
| `unknown_field_policy` | éditable | `reject` \| `ignore` \| `store` |
| `pipeline` | éditable | Config ML complète (credentials `•••`) |
| `metadata_fields` | éditable | Schéma complet (champs système + custom) |

**404** — collection inconnue.

### Tests unitaires

Fichier : `tests/api/collections/config/test_config.py` — classe `TestGetConfigState`

| Test | Ce qui est vérifié |
|---|---|
| `test_state_returns_200_for_known_collection` | Collection existante → 200 |
| `test_state_returns_404_for_unknown_collection` | `get_by_id` retourne `None` → 404 |
| `test_state_response_has_required_fields` | Body contient `id`, `name`, `pipeline_version`, `needs_reindex`, `supported_formats`, `pipeline`, `metadata_fields` |
| `test_state_id_matches_collection` | `body["id"] == str(collection_id)` |
| `test_state_pipeline_is_redacted_dict` | `body["pipeline"]` est bien un `dict` (pas une string, pas null) |

---

## GET /config/schema

Retourne la **surface configurable** du déploiement : catalogue des champs système + schéma live des providers.

### Comportement

L'existence de la collection est vérifiée (404 sinon), puis la réponse est assemblée à partir de deux sources stateless :

- **`metadata_fields`** — les 13 champs système du catalogue (`SYSTEM_METADATA_FIELDS`), indépendants de la collection. C'est ce que le client utilise pour connaître les flags de recherche configurables sur les champs système.
- **`stages`** — `registry.describe_stages()["stages"]`, le schéma live des providers disponibles dans ce déploiement : pour chaque stage, la liste des providers sélectionnables avec leur disponibilité et leurs paramètres attendus.

> Bien que le contenu de la réponse soit global au déploiement, cet endpoint est un sous-chemin de la collection (pas de `/config/schema` global) pour maintenir la cohérence de l'arborescence et permettre un contrôle d'accès par collection.

### Réponse

**200 OK**

```json
{
  "metadata_fields": [
    { "field_name": "filename",  "field_type": "string",  "filterable": true, "lexical": true, ... },
    { "field_name": "language",  "field_type": "string",  "filterable": true, ... },
    { "field_name": "page",      "field_type": "number",  "filterable": true, ... },
    ...
  ],
  "stages": [
    {
      "id": "s1",
      "name": "Parse",
      "groups": [
        {
          "capability": "parse",
          "providers": [
            { "id": "docling",  "selectable": true, "available": true,  "note": null },
            { "id": "marker",   "selectable": true, "available": false, "note": "MinerU not installed." },
            { "id": "tika",     "selectable": true, "available": true,  "note": null }
          ]
        }
      ]
    },
    ...
  ]
}
```

**404** — collection inconnue.

### Tests unitaires

Fichier : `tests/api/collections/config/test_config.py` — classe `TestGetConfigSchema`

| Test | Ce qui est vérifié |
|---|---|
| `test_schema_returns_200_for_known_collection` | Collection existante → 200 |
| `test_schema_returns_404_for_unknown_collection` | `get_by_id` retourne `None` → 404 |
| `test_schema_response_has_metadata_fields_and_stages` | Body contient `metadata_fields` et `stages` |
| `test_schema_stages_comes_from_registry` | `stages` est exactement ce que `registry.describe_stages()` retourne (passthrough fidèle, pas de filtrage) |

---

## GET /config/history

Liste l'historique des versions de config (du plus récent au plus ancien).

### Comportement

Charge la liste des snapshots depuis `config_repo.list_versions()`. Chaque version correspond à un appel passé à `/config/update` ou `/config/rollback` qui a abouti. L'ordre retourné est celui du repo (conventionnellement le plus récent en premier).

Une collection sans historique retourne `total: 0` et `versions: []` — ce n'est pas une erreur.

> Le contenu du snapshot (le `config` sérialisé) n'est **pas** inclus dans cet endpoint. C'est intentionnel : l'historique est une liste de métadonnées (quand, quelle version, quelle note). Pour restaurer une version, utiliser `/config/rollback`.

### Réponse

**200 OK**

```json
{
  "collection_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "total": 3,
  "versions": [
    { "version": 3, "pipeline_version": "v3", "note": "activation S6 embed", "created_at": "2025-03-10T14:22:00Z" },
    { "version": 2, "pipeline_version": "v2", "note": "ajout champ project_code", "created_at": "2025-02-05T09:11:00Z" },
    { "version": 1, "pipeline_version": "v1", "note": null, "created_at": "2025-01-15T10:30:00Z" }
  ]
}
```

| Champ de `ConfigVersionSummary` | Type | Description |
|---|---|---|
| `version` | int | Numéro de version séquentiel (commence à 1) |
| `pipeline_version` | string | Valeur de `collection.pipeline_version` au moment du snapshot |
| `note` | string \| null | Commentaire libre saisi lors de l'update (ou `"rollback to v{n}"` si rollback) |
| `created_at` | datetime | ISO 8601 UTC |

**404** — collection inconnue.

### Tests unitaires

Fichier : `tests/api/collections/config/test_config.py` — classe `TestGetConfigHistory`

| Test | Ce qui est vérifié |
|---|---|
| `test_history_returns_404_for_unknown_collection` | `get_by_id` retourne `None` → 404 |
| `test_history_empty_returns_200` | Aucun historique → 200, `total: 0`, `versions: []` |
| `test_history_returns_version_summaries` | Une version mockée → `total: 1`, `versions[0].version == 1` |
| `test_history_collection_id_in_response` | `body["collection_id"] == str(collection_id)` |

---

## POST /config/update

Applique un patch partiel sur la config courante, valide, et persiste.

### Comportement

**Étape 1 — Fusion** : le `patch` fourni est deep-mergé sur le document de config courant via `ConfigDocument.merge_patch()`.

Règles de merge :
- Les dicts imbriqués sont mergés récursivement : patcher `{ "pipeline": { "chunk": { "split_method": { "params": { "max_tokens": 256 } } } } }` ne touche que `max_tokens`, l'`id` de la méthode et tous les autres knobs du pipeline restent inchangés.
- Les listes et scalaires remplacent en totalité : envoyer `{ "metadata_fields": [...] }` remplace tout le schéma.

**Étape 2 — Validation** : le document mergé passe par `ConfigValidator.validate()` (identique à la création). Si au moins une issue `severity: "error"` est trouvée → **422** avec la liste des issues.

**Étape 3 — Application** : `config_repo.apply_config()` persiste le nouveau document et crée un snapshot d'historique. En interne, ce repo bumpe `pipeline_version` si le pipeline ou l'`embedding_model` ont changé et positionne `needs_reindex=true` si l'embedding model a changé.

**Patch vide** (`patch: {}`) valide : aucun champ n'est modifié, mais un snapshot est quand même créé dans l'historique (utile pour noter un "checkpoint" ou simplement déclencher une trace).

### Corps de la requête

```json
{
  "patch": {
    "pipeline": {
      "chunk": { "split_method": { "params": { "max_tokens": 256 } } },
      "embed": { "provider": { "params": { "base_url": "http://tei-ext:8080" } } }
    }
  },
  "note": "réduit la taille des chunks + bascule l'embedding sur un endpoint externe"
}
```

| Champ | Type | Défaut | Description |
|---|---|---|---|
| `patch` | dict | `{}` | Document partiel. Seules les clés fournies remplacent l'existant. |
| `note` | string \| null | `null` | Commentaire libre enregistré dans l'historique. |

### Codes de retour

| Code | Condition |
|---|---|
| **200 OK** | Patch appliqué — retourne `ConfigStateResponse` avec la nouvelle config |
| **404 Not Found** | Collection inconnue |
| **422 Unprocessable Entity** | Le document mergé contient des issues `severity: "error"` (même catalogue que `POST /collections/create`) |

La réponse 200 est identique à `GET /config/state` après le changement (pipeline redacté + défauts
résolus), **enrichie du champ commun `applied`** : `provided`/`defaulted` (ce que le patch a touché vs
laissé par défaut), `pipeline` par section (`provided`/`default`), `metadata_fields` (compte
système/custom), `overridden_system_fields`, `needs_reindex`, `warnings` (issues non bloquantes) et
`notes`. Même enveloppe qu'à la création et au rollback — la transparence est uniforme sur tous les
endpoints de config. (`GET /config/state` seul n'a pas d'action → `applied: null`.)

### Tests unitaires

Fichier : `tests/api/collections/config/test_config.py` — classe `TestUpdateConfig`

| Test | Ce qui est vérifié |
|---|---|
| `test_update_returns_404_for_unknown_collection` | `get_by_id` retourne `None` → 404 |
| `test_update_returns_200_on_success` | Patch valide + `apply_config` → 200 |
| `test_update_response_is_config_state` | Body contient `id` et `pipeline_version` (shape `ConfigStateResponse`) |
| `test_update_empty_patch_is_valid` | `patch: {}` → 200 (le no-op est accepté) |

> **Périmètre** : `ConfigValidator.validate` est neutralisé dans tous les tests API (`return_value = []`). Le cas 422 du validator n'est pas testé à ce niveau.

---

## POST /config/rollback

Restaure une version précédente de la config en la ré-appliquant comme une nouvelle version.

### Comportement

**Ce que le rollback N'EST PAS** : une réécriture de l'historique. La ligne de la version cible n'est pas modifiée.

**Ce que le rollback EST** : le contenu du snapshot `version` est récupéré, re-validé par `ConfigValidator` (les providers ou contraintes peuvent avoir changé depuis), puis appliqué via le même chemin que `/config/update` — ce qui crée une **nouvelle entrée** dans l'historique avec la note `"rollback to v{version}"`.

Le résultat : l'historique contient l'ancienne version + toutes les versions intermédiaires + la nouvelle version qui est une copie de l'ancienne.

**Étapes** :
1. Charge la collection (404 si inconnue).
2. Charge le snapshot `version` depuis `config_repo.get_version()` (404 si version inconnue).
3. Valide `snapshot.config` via `ConfigValidator` (422 si invalide — cas rare mais possible si le déploiement a changé).
4. Applique via `config_repo.apply_config()` avec note `"rollback to v{version}"`.

### Corps de la requête

```json
{
  "version": 2
}
```

| Champ | Type | Contraintes | Description |
|---|---|---|---|
| `version` | int | `>= 1` | Numéro de la version à restaurer (voir `/config/history`) |

### Codes de retour

| Code | Condition |
|---|---|
| **200 OK** | Rollback réussi — retourne `ConfigStateResponse` avec la config restaurée |
| **404 Not Found** (1) | Collection inconnue |
| **404 Not Found** (2) | Version introuvable dans l'historique de cette collection |
| **422 Unprocessable Entity** | La config du snapshot est devenue invalide dans le déploiement actuel |

### Tests unitaires

Fichier : `tests/api/collections/config/test_config.py` — classe `TestRollbackConfig`

| Test | Ce qui est vérifié |
|---|---|
| `test_rollback_returns_404_for_unknown_collection` | `get_by_id` retourne `None` → 404 |
| `test_rollback_returns_404_for_unknown_version` | `config_repo.get_version` retourne `None` → 404 |
| `test_rollback_returns_200_on_success` | Snapshot valide → 200 (le snapshot fournit un dict complet pour éviter une ValidationError dans ConfigValidator) |
| `test_rollback_version_must_be_positive` | `version: 0` → 422 Pydantic (`ge=1`) |

> **Note de setup** : dans `test_rollback_returns_200_on_success`, `snapshot.config` est un dict complet (tous les champs de `PipelineConfig` présents), pas un `MagicMock` vide. Cela est nécessaire parce que le test n'est **pas** en mode neutralisation du validator — `ConfigDocument.from_collection()` et `PipelineConfig.from_dict()` s'exécutent réellement.

---

## Flux complet — cycle de vie d'une config

```
POST /collections/create
  → pipeline_version = "v1", needs_reindex = false, history = []

POST /config/update  (patch: { "pipeline": { "chunk": { "split_method": { "params": { "max_tokens": 256 } } } } })
  → pipeline_version = "v2" (pipeline changé), needs_reindex = false
  → history entry v1 créée

POST /config/update  (patch: { "embedding_model": "custom-embed" })
  → pipeline_version = "v3", needs_reindex = TRUE (embedding model changé)
  → history entry v2 créée

GET /config/history  → total: 2, versions: [v2, v1]

POST /config/rollback  (version: 1)
  → re-applique snapshot v1, pipeline_version = "v4"
  → needs_reindex = false (embedding model revenu au défaut)
  → history entry v3 créée (note: "rollback to v1")

GET /config/history  → total: 3, versions: [v3, v2, v1]
```
