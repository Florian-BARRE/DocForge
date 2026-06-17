# Collections — API Reference

Préfixe commun : `/api/v1`

---

## GET /collections/list

Liste toutes les collections existantes.

### Comportement

Charge la totalité des collections depuis Postgres dans l'ordre d'insertion (plus récent en dernier). Aucun filtrage, aucune pagination — le nombre de collections est supposé raisonnable (dizaines).

### Réponse

**200 OK** — toujours (table vide incluse)

```json
{
  "collections": [
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "name": "Rapports annuels",
      "supported_formats": ["pdf", "docx"],
      "max_file_size_bytes": 104857600,
      "max_pages": null,
      "locality_policy": "external_allowed",
      "embedding_model": "BAAI/bge-m3",
      "pipeline_version": "v1",
      "created_at": "2025-01-15T10:30:00Z"
    }
  ],
  "total": 1
}
```

| Champ | Type | Description |
|---|---|---|
| `id` | UUID | Identifiant opaque de la collection |
| `name` | string | Nom humain unique |
| `supported_formats` | string[] | Extensions acceptées à l'ingestion |
| `max_file_size_bytes` | int | Plafond de taille du fichier original |
| `max_pages` | int \| null | Plafond de pages (`null` = illimité) |
| `locality_policy` | string | Contrainte réseau pour les providers |
| `embedding_model` | string | Modèle d'embedding (fixe l'espace vectoriel) |
| `pipeline_version` | string | Version de config courante (incrémenté à chaque PATCH de config) |
| `created_at` | datetime | ISO 8601 UTC |

### Tests unitaires

Fichier : `tests/api/collections/test_collections.py` — classe `TestListCollections`

| Test | Ce qui est vérifié |
|---|---|
| `test_list_empty_returns_200` | Table vide → 200, `collections: []`, `total: 0` |
| `test_list_returns_all_collections` | 3 collections mockées → `total: 3`, 3 entrées dans la liste |
| `test_list_response_has_required_fields` | Chaque entrée expose au minimum `id`, `name`, `pipeline_version`, `created_at` |

---

## POST /collections/create

Crée une nouvelle collection et fixe son contrat (formats admis, schéma de métadonnées, pipeline).

### Comportement

**Étape 1 — Fusion du schéma de métadonnées**

Les 13 champs système sont *toujours* injectés côté serveur, quelle que soit la valeur de `metadata_schema` dans le corps. Le client n'envoie que ses champs métier personnalisés.

Règles de fusion :
- Un champ personnalisé dont le `field_name` coïncide avec un champ système **surcharge uniquement ses flags de recherche** (`filterable`, `lexical`, `semantic`, `weight_lexical`, `weight_semantic`) ; il reste marqué `is_system: true`.
- Tout autre champ est ajouté en tant que champ custom (`is_system: false`).
- L'ordre final : champs système d'abord, champs custom ensuite.

**Champs système injectés automatiquement (13) :**

| `field_name` | `field_type` | Indexé dans | Extrait par |
|---|---|---|---|
| `filename` | string | filterable + lexical | S0 |
| `extension` | string | filterable | S0 |
| `file_size` | number | filterable | S0 |
| `has_scanned_pages` | bool | filterable | S0 |
| `language` | string | filterable | S1 (Docling) |
| `page_count` | number | filterable | S1 |
| `n_blocks` | number | filterable | S1 |
| `n_figures` | number | filterable | S2 |
| `n_tables` | number | filterable | S1 |
| `page` | number | filterable | S4 chunk prov. |
| `heading_path` | string | filterable + semantic | S4 chunk prov. |
| `block_type` | string | filterable | S4 chunk prov. |
| `token_count` | number | filterable | S4 chunk prov. |

**Étape 2 — Validation du pipeline**

Le pipeline est validé contre le schéma live des providers (`registry.describe_stages()`). La création est rejetée si au moins une issue de sévérité `error` est trouvée.

**Étape 3 — Persistance**

La collection est insérée en Postgres. Un conflit de nom unique (`IntegrityError`) est transformé en 409.

### Corps de la requête

```json
{
  "name": "Rapports annuels",
  "supported_formats": ["pdf", "docx"],
  "max_file_size_bytes": 104857600,
  "max_pages": null,
  "locality_policy": "external_allowed",
  "embedding_model": "BAAI/bge-m3",
  "unknown_field_policy": "reject",
  "pipeline": {},
  "metadata_schema": [
    {
      "field_name": "project_code",
      "field_type": "string",
      "required": true,
      "filterable": true
    }
  ]
}
```

| Champ | Type | Défaut | Contraintes |
|---|---|---|---|
| `name` | string | **requis** | 1–255 caractères |
| `supported_formats` | string[] | `["pdf","docx","doc","xlsx","pptx","ppt","odt","rtf"]` | |
| `max_file_size_bytes` | int | `104857600` (100 MB) | > 0 |
| `max_pages` | int \| null | `null` | > 0 si renseigné |
| `locality_policy` | enum | `"external_allowed"` | `on_premise_only` \| `external_allowed` |
| `embedding_model` | string | `"BAAI/bge-m3"` | non vide |
| `unknown_field_policy` | enum | `"reject"` | `reject` \| `ignore` \| `store` |
| `pipeline` | dict | `{}` | voir Validation pipeline |
| `metadata_schema` | MetaFieldSpec[] | `[]` | voir Schéma métadonnées |

**MetaFieldSpec :**

| Champ | Type | Défaut | Contraintes |
|---|---|---|---|
| `field_name` | string | requis | 1–255 chars |
| `field_type` | enum | `"string"` | `string` \| `number` \| `date` \| `bool` \| `enum` \| `string[]` |
| `required` | bool | `false` | |
| `filterable` | bool | `false` | Payload Qdrant |
| `lexical` | bool | `false` | Vecteur sparse BM25 dédié |
| `semantic` | bool | `false` | Vecteur dense dédié |
| `weight_lexical` | float | `1.0` | [0.0, 10.0] |
| `weight_semantic` | float | `1.0` | [0.0, 10.0] |
| `enum_values` | string[] \| null | `null` | Obligatoire si `field_type="enum"` |

### Codes de retour

| Code | Condition |
|---|---|
| **201 Created** | Succès — retourne `CollectionResponse` |
| **409 Conflict** | Un nom identique existe déjà |
| **422 Unprocessable Entity** | Validation Pydantic (nom manquant/vide, enum invalide) **ou** pipeline invalide (voir tableau ci-dessous) |

### Erreurs de validation du pipeline (`severity: "error"` → rejet)

| Code d'issue | Champ | Condition |
|---|---|---|
| `pipeline.invalid` | `pipeline` | Pipeline non parseable (structure malformée) |
| `locality.remote_ocr` | `enrich.ocr_chain` | OCR cloud (`mistral_ocr`) avec `on_premise_only` |
| `locality.remote_vlm` | `enrich.vlm` | URL VLM publique avec `on_premise_only` |
| `locality.remote_embed` | `embed.provider` | URL d'embedding publique avec `on_premise_only` |
| `{capability}.unknown` | capability | Provider/méthode inconnu du registry |
| `{capability}.not_selectable` | capability | Provider non sélectionnable dans ce déploiement |
| `metadata.no_name` | `metadata_fields` | Champ sans `field_name` |
| `metadata.duplicate` | `metadata_fields.{name}` | Nom de champ dupliqué |
| `metadata.bad_type` | `metadata_fields.{name}` | `field_type` hors des valeurs autorisées |
| `metadata.enum_empty` | `metadata_fields.{name}` | Champ `enum` sans `enum_values` |
| `metadata.bad_weight` | `metadata_fields.{name}.weight_*` | Poids RRF hors de [0.0, 10.0] |

> `capability` ∈ `parse` · `classifier` · `ocr` · `vlm` · `embed` · `chunk_strategy` (méthode de découpage S4 : `token_budget` · `semantic` · `sentence_window`).
> Exemple : `chunk_strategy.unknown` si `chunk.split_method.id` est inconnu ; `chunk_strategy.unavailable` (avertissement) si `semantic` est choisi mais TEI n'est pas joignable et qu'aucun `base_url` n'est fourni.

**Avertissements (non bloquants) :**

| Code d'issue | Condition |
|---|---|
| `enrich.chart_to_data_inert` | `chart_to_data=true` mais S2 désactivé |
| `enrich.providers_inert` | OCR/VLM configurés mais S2 désactivé |
| `{capability}.unavailable` | Provider sélectionnable mais non disponible actuellement, sans credentials dans les params |

La réponse 422 inclut le détail complet :

```json
{
  "detail": {
    "message": "Invalid pipeline configuration.",
    "issues": [
      {
        "code": "chunk_strategy.unknown",
        "severity": "error",
        "field": "chunk_strategy",
        "message": "Unknown chunk_strategy provider 'foo'."
      }
    ]
  }
}
```

### Réponse 201

La création renvoie l'**état de config complet résolu** (mêmes champs que `GET …/config/state`) :
le `pipeline` est rempli avec les défauts (les knobs omis sont explicités), `metadata_fields`
contient les champs système injectés + tes champs custom, et un champ commun **`applied`** détaille
ce qui a été fourni vs mis par défaut. Le pipeline est crédentiel-masqué.

```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "name": "Rapports annuels",
  "pipeline_version": "v1",
  "needs_reindex": false,
  "supported_formats": ["pdf", "docx"],
  "max_file_size_bytes": 104857600,
  "locality_policy": "external_allowed",
  "embedding_model": "BAAI/bge-m3",
  "unknown_field_policy": "reject",
  "pipeline": { "parse": { "...": "résolu" }, "enrich": { "...": "..." }, "chunk": { "...": "..." }, "embed": { "...": "..." } },
  "metadata_fields": [ { "field_name": "filename", "is_system": true, "filterable": true, "lexical": true, "...": "..." } ],
  "created_at": "2025-01-15T10:30:00Z",
  "applied": {
    "provided": ["name", "pipeline"],
    "defaulted": ["supported_formats", "max_file_size_bytes", "locality_policy", "embedding_model", "unknown_field_policy", "metadata_fields"],
    "pipeline": { "parse": "default", "enrich": "default", "chunk": "provided", "embed": "default" },
    "metadata_fields": { "system": 12, "custom": 0 },
    "overridden_system_fields": [],
    "needs_reindex": false,
    "warnings": [],
    "notes": ["Filled from defaults: …", "12 system metadata fields auto-injected; 0 custom field(s)."]
  }
}
```

> **`applied` — enveloppe de transparence commune** (présente aussi sur `config/update` et `config/rollback`) :
> `provided`/`defaulted` (clés top-level), `pipeline` (par section : `provided`/`default`),
> `metadata_fields` (compte système/custom), `overridden_system_fields`, `needs_reindex`,
> `warnings` (issues non bloquantes), `notes` (résumé lisible). Tu peux ainsi vérifier exactement
> ce que le serveur a appliqué et ce qui vient des défauts — aucun comportement implicite caché.

### Tests unitaires

Fichier : `tests/api/collections/test_collections.py` — classe `TestCreateCollection`

| Test | Ce qui est vérifié |
|---|---|
| `test_create_returns_201` | Body valide → 201 |
| `test_create_response_has_id_and_name` | La réponse contient `id` et `name` correspondant au body envoyé |
| `test_create_duplicate_name_returns_409` | `collection_repo.create` lève `IntegrityError` → 409 |
| `test_create_missing_name_returns_422` | Body sans champ `name` → 422 (validation Pydantic) |
| `test_create_empty_name_returns_422` | `name: ""` → 422 (contrainte `min_length=1`) |

> **Périmètre limité** : La validation pipeline par `ConfigValidator` est neutralisée dans tous les tests API via `monkeypatch` (`ConfigValidator.validate` renvoie toujours `[]`). Les cas d'erreur du validator (embed sans chunk, conflit locality, provider inconnu, poids hors range, etc.) sont couverts dans `tests/api/collections/config/test_config.py` — voir la doc de la config route.

---

## DELETE /collections/{collection_id}/delete

Supprime une collection et l'intégralité de ses données associées.

### Comportement

**Étape 1 — Résolution** : charge la collection ; 404 si absente.

**Étape 2 — Audit des blobs S3** : collecte tous les `source_hash` des documents de la collection et détermine lesquels sont *partagés* avec d'autres collections. Le stockage est content-addressed : le même fichier uploadé dans deux collections partage le même `source_hash` et donc le même blob.

**Étape 3 — Suppression S3 sélective** : pour chaque hash *non partagé* :
- supprime `originals/{source_hash}` (fichier original)
- supprime le préfixe `derived/{source_hash}/` (PDF converti, markdown, screenshots de pages)

Les blobs partagés ne sont pas touchés.

**Étape 4 — Suppression Qdrant** : si Qdrant est actif, la collection vectorielle (nommée par `collection_id`) est droppée avec tous ses points.

**Étape 5 — Suppression Postgres** : suppression en cascade de tous les documents, blocks, chunks, jobs, champs de métadonnées et stage_runs liés à la collection.

### Paramètres

| Paramètre | In | Type | Description |
|---|---|---|---|
| `collection_id` | path | UUID | Identifiant de la collection à supprimer |

### Codes de retour

| Code | Condition |
|---|---|
| **200 OK** | Suppression réussie |
| **404 Not Found** | `collection_id` inconnu |

### Réponse 200

```json
{
  "deleted": true,
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
}
```

### Règle de partage des blobs

```
is_source_hash_shared(hash, collection_id)
  → True  : le hash est encore référencé par au moins une autre collection
             → blob conservé
  → False : ce hash est unique à la collection en cours de suppression
             → blob supprimé (original + tous les dérivés)
```

Cette vérification est effectuée *avant* la suppression des lignes Postgres, ce qui garantit une décision cohérente même en cas de suppression concurrente.

### Tests unitaires

Fichier : `tests/api/collections/test_collections.py` — classe `TestDeleteCollection`

| Test | Ce qui est vérifié |
|---|---|
| `test_delete_existing_returns_200` | Collection connue, aucun blob associé → 200 |
| `test_delete_missing_collection_returns_404` | `collection_repo.get_by_id` retourne `None` → 404 |
| `test_delete_response_deleted_true` | Body de la réponse contient `deleted: true` |
| `test_delete_response_id_matches` | Body `id` correspond au `collection_id` du path |
| `test_delete_skips_shared_blobs` | Un hash retourné mais `is_source_hash_shared → True` → 200 et `s3.delete` non appelé |

> **Ce qui n'est pas testé ici** : la suppression effective du blob S3 quand le hash n'est pas partagé n'est pas vérifiée par assertion (seul le flux `shared → skip` est asserté). Le drop Qdrant et la cascade Postgres ne sont pas assertés non plus — ils passent silencieusement via les mocks.
