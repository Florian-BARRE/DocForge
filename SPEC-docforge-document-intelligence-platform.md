# DocForge — Plateforme de Document Intelligence & Retrieval

**Spécification technique complète — v1.0 (juin 2026)**
*Nom du projet : **DocForge**.*

---

## 0. Résumé exécutif

DocForge est une stack complète, self-hostable et **entièrement paramétrable** de traitement documentaire pour la GenAI : conversion multi-format → représentation intermédiaire structurée (IR) à provenance → enrichissement OCR/VLM routé intelligemment → chunking structure-aware → indexation hybride (dense + sparse multi-champs pondéré) → retrieval avancé exposé via API REST, MCP et UI.

**Positionnement.** DocForge ne réimplémente pas les modèles de parsing (layout, tables, OCR) : il orchestre les meilleurs backends existants (Docling, MinerU, Marker, olmOCR-2, Qwen-VL, Mistral OCR…) derrière des **interfaces interchangeables**, et construit la couche qui n'existe nulle part : orchestration paramétrable par collection, IR à provenance propagée de bout en bout, double cache content-addressed, retrieval hybride multi-champs configurable, et features de provenance servies au runtime (screenshot de la page d'un passage, PDF source, contenu brut/OCR/description au choix du client).

**Principes structurants :**
1. **L'IR est la couche canonique** ; markdown, PDF propre, HTML ne sont que des *vues* sérialisées.
2. **Toute brique ML est un provider interchangeable** (local GPU / local CPU / API externe) derrière une interface fine, l'API OpenAI-compatible servant de lingua franca.
3. **Tout dérivé est une fonction pure de `(original, config)`**, versionné par empreinte de stage (Merkle-DAG) — reindex incrémental, reprise sur crash et dry-run en découlent gratuitement.
4. **La Collection est le contrat central** : schéma de métadata + règles d'admission + pipeline + politique de confidentialité + défauts de retrieval.
5. **La métadata a trois rôles distincts** (filtrer / contextualiser / afficher-prouver) matérialisés sous trois formes différentes.
6. **Le routage intelligent minimise les coûts** : seul ce qui nécessite OCR/VLM part vers les modèles (locaux ou payants).

---

## 1. Architecture globale

```
                    ┌────────────┐  ┌────────────┐  ┌──────────────────────┐
                    │  UI React  │  │ MCP Server │  │ REST API             │
                    │ (playground│  │ (agents    │  │ (natif + shim        │
                    │  + admin)  │  │  GenAI)    │  │  Docling-compat)     │
                    └──────┬─────┘  └─────┬──────┘  └──────────┬───────────┘
                           └──────────────┼────────────────────┘
                                          │
                              ┌───────────▼───────────┐
                              │  API Gateway (FastAPI) │
                              │  admission gate ·      │
                              │  collections · search  │
                              └───────────┬───────────┘
              ┌───────────────┬───────────┼────────────┬───────────────┐
              ▼               ▼           ▼            ▼               ▼
        ┌──────────┐   ┌───────────┐ ┌─────────┐ ┌──────────┐  ┌─────────────┐
        │ Postgres │   │ Job queue │ │ Stage   │ │ Provider │  │ Object store│
        │ (catalog,│   │ (arq)     │ │ engine  │ │ registry │  │ MinIO/S3    │
        │ metadata,│   │           │ │ (Merkle │ │ (local/  │  │ (originals, │
        │ chunks,  │   │           │ │  DAG +  │ │  API)    │  │ PNG pages,  │
        │ caches)  │   │           │ │  caches)│ │          │  │ crops, vues)│
        └──────────┘   └───────────┘ └────┬────┘ └──────────┘  └─────────────┘
                                          │
                                    ┌─────▼─────┐
                                    │  Qdrant   │  named dense vectors +
                                    │ (vectors) │  sparse BM25 multi-champs +
                                    └───────────┘  payload filtrable in-graph
```

**Déploiement v1 : monolithe modulaire + workers.** Un service API, un pool de workers (les tâches GPU/API lourdes passent par la file), les 3 stores. Les frontières de découpe futures sont les frontières de scaling réelles : workers de parsing GPU, service d'embedding.

### Stores et rôles (séparation stricte)

| Store | Rôle | Nature |
|---|---|---|
| **Postgres 16** | Catalogue (collections, documents, blocs/IR, chunks, schémas de métadata, stage_runs, provider_calls, jobs, ACL) | **Source de vérité relationnelle** |
| **MinIO/S3** | Blobs content-addressed : originaux, PDF dérivés, PNG par page, crops de figures, vues markdown/PDF, artefacts IR sérialisés | Vérité (originaux) + dérivés régénérables |
| **Qdrant** | Vecteurs nommés (dense multi-champs) + sparse (BM25 multi-champs) + payload de filtrage | **Index dérivé, reconstructible** depuis Postgres + blobs ; jamais source de vérité |

---

## 2. La représentation intermédiaire (IR)

### 2.1 Principe

Le pivot du système n'est **pas** le markdown (plat, avec perte) mais un **arbre de blocs typés** portant : type, contenu natif, provenance (page, bbox), ordre de lecture, hiérarchie de titres, et **slots d'enrichissement** remplis par la pipeline. Le markdown fidèle est *généré depuis* l'IR, jamais l'inverse.

La vue plate sérialisée reste **pure structure fidèle** : elle ne contient aucune description générée. Les enrichissements (OCR, description VLM, données de chart) sont des **propriétés du nœud IR**, injectées uniquement dans le texte d'embedding si activé, et restituables séparément au retrieval (le client choisit : brut / OCR / description / crop).

### 2.2 Schéma (pydantic — code et commentaires en anglais)

```python
from enum import Enum
from pydantic import BaseModel


class BlockType(str, Enum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"
    FIGURE = "figure"
    CAPTION = "caption"
    CODE = "code"
    FORMULA = "formula"
    HEADER_FOOTER = "header_footer"   # detected, excluded from chunks by default


class FigureKind(str, Enum):
    SCANNED_TEXT = "scanned_text"     # text rendered as image (scan region)
    CHART = "chart"                   # data visualization (bar, line, pie...)
    DIAGRAM = "diagram"               # schema, flow, architecture drawing
    PHOTO = "photo"                   # photographic / illustrative content
    DECORATIVE = "decorative"         # logo, banner, separator -> skipped


class Provenance(BaseModel):
    page: int
    bbox: tuple[float, float, float, float]   # normalized x0, y0, x1, y1
    char_span: tuple[int, int] | None = None   # span within the serialized view


class FigureEnrichment(BaseModel):
    kind: FigureKind
    crop_key: str                              # object-store key of the cropped image
    relevance: float                           # classifier score; gates VLM/OCR calls
    ocr_text: str | None = None                # text extracted from inside the figure
    description: str | None = None             # VLM caption, grounded on ocr_text + image
    data_table: list[list[str]] | None = None  # chart-to-data extraction, when applicable


class TableData(BaseModel):
    cells: list[list[str]]                     # structured cells (native or TableFormer)
    n_rows: int
    n_cols: int
    has_header: bool


class Block(BaseModel):
    id: str
    type: BlockType
    prov: Provenance
    reading_order: int
    parent_id: str | None = None               # heading hierarchy (tree)
    level: int | None = None                   # heading level
    text: str | None = None                    # native text content
    table: TableData | None = None             # for TABLE blocks
    figure: FigureEnrichment | None = None     # for FIGURE blocks
    language: str | None = None                # per-block language if mixed


class DocumentIR(BaseModel):
    doc_id: str
    source_hash: str                           # sha256 of the original file
    pipeline_fingerprints: dict[str, str]      # stage name -> fingerprint
    n_pages: int
    language: str
    blocks: list[Block]
```

`parent_id` + `level` ⇒ arbre de titres (chunking structure-aware + breadcrumb). `prov` ⇒ screenshots et localisation de passage. `figure` ⇒ tout l'enrichissement, rattaché proprement au bloc.

---

## 3. La Collection : le contrat central

Analogie : **une Collection est aux documents ce qu'une table SQL typée est aux lignes** — schéma + contraintes (`NOT NULL`/`CHECK`) + trigger d'ingestion + définition d'index, en un seul objet déclaratif, versionné.

```python
class MetaField(BaseModel):
    name: str
    type: Literal["string", "number", "date", "bool", "enum", "string[]"]
    required: bool = False
    # --- three orthogonal search capabilities ---
    filterable: bool = False        # promoted to indexed vector-store payload
    lexical: bool = False           # dedicated BM25 sparse vector
    semantic: bool = False          # dedicated named dense vector
    weight_lexical: float = 1.0     # fusion weight (RRF) when lexical
    weight_semantic: float = 1.0    # fusion weight when semantic
    enum_values: list[str] | None = None


class Collection(BaseModel):
    id: str
    name: str
    # --- ADMISSION CONTRACT (validated before any processing) ---
    supported_formats: list[str]                  # e.g. ["pdf","docx","doc","xlsx","pptx"]
    max_file_size_bytes: int
    max_pages: int | None = None
    metadata_schema: list[MetaField]              # business fields (user payload)
    unknown_field_policy: Literal["reject", "ignore", "store"] = "reject"
    # --- INGESTION PIPELINE (frozen playground assembly) ---
    pipeline: PipelineConfig
    pipeline_version: str                         # bumped on any pipeline change
    # --- GOVERNANCE ---
    locality_policy: Literal["on_premise_only", "external_allowed"]
    allowed_providers: list[str] = []             # allowlist when external_allowed
    # --- RETRIEVAL DEFAULTS ---
    default_search: SearchConfig
    embedding_model: str                          # fixed per collection (vector space!)


class PipelineConfig(BaseModel):
    convert: ProviderRef          # Gotenberg
    parse: ProviderRef            # Docling | MinerU | Marker (+ mode)
    enrich: EnrichConfig          # figure classifier, ocr, vlm, chart_to_data
    chunk: ChunkConfig            # strategy, max_tokens, overlap, contextualize
    embed: ProviderRef


class ProviderRef(BaseModel):
    capability: str                               # "ocr" | "vlm" | "embed" | "rerank" | ...
    chain: list[ProviderSpec]                     # escalation chain (see §6)
    device_fallback: list[Literal["gpu", "cpu", "api"]]  # per-brick order
```

**Règles non négociables :**
- **Validation statique à la création** : une collection `on_premise_only` dont la pipeline référence un provider API est une config **invalide** rejetée à la sauvegarde — pas au premier document parti chez un tiers.
- `embedding_model` est **figé par collection** (un espace vectoriel = un modèle). En changer = nouvelle `pipeline_version` + reindex.
- Le schéma est **auto-documenté** : `GET /collections/{id}/schema` expose formats, champs requis, types — le contrat se lit tout seul.

---

## 4. La pipeline (stages S0 → S6)

```
S0 ingest        original content-addressed (sha256) + config snapshot
S1 parse         -> IR (typed blocks + order + bbox + hierarchy)
                 -> page PNG renders + figure crops
S2 enrich        per-element routing; fills IR figure slots (OCR/VLM/chart-to-data)
S3 serialize     IR -> faithful markdown (+ clean PDF, + HTML) = VIEWS (leaf)
S4 chunk         structure-aware over the enriched IR -> chunks (raw_text + provenance)
S5 contextualize breadcrumb + optional LLM situating sentence -> embed_text
S6 embed+index   dense + sparse vectors -> vector store (idempotent upsert)
```

⚠️ **S4 dépend de S2, pas de S3** : le chunking opère sur l'IR enrichi ; le markdown est une feuille de l'arbre (vue humaine/tierce), rien en aval ne le consomme.

### 4.1 S0 — Ingestion & conversion

- Original stocké par `sha256(content)` → dédup, idempotence, immutabilité.
- **Routage par format** (le piège à éviter : tout faire transiter par le PDF) :
  - **Tableurs (xlsx/xls/csv)** → parsing **natif** vers l'IR (cellules structurées). Jamais via PDF (pagination artificielle destructrice).
  - **Doc-like (docx/doc/pptx/ppt/odt/rtf…)** → double chemin **parallèle** : (a) parsing natif quand le backend le supporte (fidélité des données), (b) conversion **Gotenberg** → PDF pour pagination + screenshots + vue d'affichage.
  - **PDF** → direct S1.
  - **Formats exotiques** (mails, archives…) → fallback **Apache Tika/Extractous** basse fidélité (couverture).
- **Conversion : Gotenberg, seul.** Gotenberg = LibreOffice + Chromium derrière une API HTTP ops-grade (isolation process, queue, Docker, MIT) ; il apporte aussi gratuitement les opérations PDF (merge/split/PDF-A/page ranges) utiles à la vue propre. Macros désactivées par défaut, filtrage URL sortant configurable. *(Décision : pas de Collabora en fallback — best-effort legacy assumé ; escape hatch documenté si un corpus pathologique l'exige un jour.)*
- Extraction de la **métadata implicite file-intrinsèque** (cf. §7.3).

### 4.2 S1 — Parsing → IR

- **Fork natif/raster** (premier embranchement, avant toute question OCR/VLM) : `PyMuPDF.get_text()` vide sur une page ⇒ page scannée ⇒ flag raster. Les pages à couche texte native ne touchent **jamais** un modèle de vision.
- **Backend pluggable** derrière `ParserBackend` :
  - **Docling** (défaut) : IR à hiérarchie sémantique + bboxes ; TableFormer ≈ 91 % TEDS (FinTabNet, mode ACCURATE) ; fidélité structurelle quasi parfaite.
  - **MinerU** (routé) : scientifique, formules (UniMERNet > 90 % BLEU), CJK.
  - **Marker** (routé) : documents hétérogènes/messy, multi-format.
- Sortie : `DocumentIR` + rendus **PNG par page** + **crops de figures** (par bbox), tous poussés dans l'object store.
- Mapping backend → IR : chaque backend a son adapter qui traduit sa sortie vers le schéma IR commun.

### 4.3 S2 — Enrichissement (routage par élément)

Le classifieur de figures (petit ViT local CPU/GPU, ou labels du modèle de layout) route chaque région raster :

| Type détecté | OCR | VLM | Extra |
|---|---|---|---|
| Page scannée / texte-image | ✅ récupération texte | — | — |
| **Chart/graphique** | ✅ labels + chiffres | ✅ description **groundée** sur l'OCR | **chart-to-data** : séries → `data_table` |
| **Schéma/diagramme** | ✅ labels internes | ✅ description sens/flux groundée | — |
| Photo/illustration | — | ✅ description seule | — |
| Logo/décoratif | — | — | **skip** (gate de pertinence : ne jamais embedder) |

**Grounding anti-hallucination** : la sortie OCR est passée dans le prompt du VLM avec consigne stricte de n'inventer aucun chiffre absent de l'OCR. La description est rédigée **pour le retrieval** (axes, unités, tendances, extrema — ce que les requêtes matcheront).

**Chart-to-data** : un graphique décrit est *cherchable* ; un graphique tabulé est *interrogeable*. Extraction des séries en table/JSON via le VLM (sortie structurée).

Une figure significative devient **son propre chunk** : `embed_text = ocr_text + description + data_table aplatie`, pointant vers `crop_key` pour l'affichage.

Tous les appels OCR/VLM passent par le **provider-call cache** (§5.3) — un crop déjà vu n'est jamais re-payé.

### 4.4 S3 — Sérialisation (vues)

- **Markdown fidèle** : structure pure, sans aucune description générée. Les figures y apparaissent comme blocs image référencés par `block_id` — le lien vers l'enrichissement se fait par id, pas par injection de texte.
- **PDF propre** et HTML : autres vues optionnelles.
- Pour les sources non-PDF, l'`original→PDF` (S0) sert aussi de base aux rendus PNG par page ⇒ prérequis de la feature screenshot sur les fichiers Office.

### 4.5 S4 — Chunking (structure-aware)

- **Défaut : recursive structure-aware piloté par la hiérarchie de l'IR** (pas des `\n\n` aveugles). Une section = une unité ; si elle dépasse le budget (~512 tokens par défaut), split récursif.
- **Overlap configurable, pas activé aveuglément** : inutile avec le retrieval sparse, utile surtout en dense long-contexte — à mesurer sur le corpus.
- Stratégies additionnelles disponibles (knobs) : semantic, page-level, hierarchical small-to-big, agentic (coût 10–50×, réservé aux cas mesurés).
- Les blocs `HEADER_FOOTER` et figures `DECORATIVE` sont exclus par défaut.
- Chaque chunk garde `block_ids[]` + provenance agrégée complète. Non négociable.

### 4.6 S5 — Contextualisation

Découplage strict : `raw_text` (fidèle, affiché/cité) ≠ `embed_text` (augmenté, vectorisé).

```
embed_text =
    f"{doc_title}\n"
    f"{heading_breadcrumb}\n"          # e.g. "Section 2 > 2.1 Methodology"
    f"{llm_situating_sentence}\n"      # optional contextual retrieval, if enabled
    + chunk_body
# chunk_body for a figure block = ocr_text + vlm_description + flattened data_table
```

Le contextual retrieval (phrase de situation générée par LLM) est un knob par collection — gain de rappel documenté (jusqu'à −67 % d'échecs de retrieval), coût LLM à l'ingestion, appels memoizés.

### 4.7 S6 — Embedding & indexation

- Embedding de `embed_text` (dense) + génération des sparse vectors (content + champs `lexical`) + dense additionnels (champs `semantic`).
- **Upsert idempotent par `chunk_id`** dans Qdrant : ré-exécution à empreinte égale = no-op. L'écriture dans l'index est un side-effect de matérialisation ; la vérité reste Postgres.

---

## 5. Le moteur de stages (Merkle-DAG + double cache)

### 5.1 Fingerprint

Empreinte calculée **avant** exécution (dépend des entrées, pas de la sortie) :

```python
def fingerprint(node, inputs) -> str:
    return blake3(
        node.type,
        node.code_version,               # node logic version
        canonical_json(node.params),     # node config from collection.pipeline
        *[fp(i) for i in inputs],        # upstream fingerprints -> Merkle chain
    )

fp = fingerprint(node, inputs)
if (artifact := node_cache.get(fp)) is not None:
    return artifact                      # HIT: skip, zero cost
artifact = node.execute(inputs, node.params)
node_cache.put(fp, artifact)             # atomic: full artifact or nothing
return artifact
```

Racine = `source_hash`. Changer un param de chunking ⇒ seules les empreintes S4/S5/S6 changent ⇒ parse + enrich (le GPU/API coûteux) restent en cache. **Le reindex est incrémental par construction.**

### 5.2 Les deux caches (à ne pas confondre)

| Cache | Clé | Donne |
|---|---|---|
| **Node cache** | `(document_id, node_id, fingerprint)` | Reindex incrémental ; reprise sur crash (relance = reprend au nœud manquant) |
| **Provider-call cache** | `blake3(capability, provider_id, provider_version, params, content_hash)` | Dédup **inter-documents** : un crop (logo répété sur 1000 docs) OCR/VLM-isé et facturé **une seule fois** ; un chunk identique embeddé une fois |

```python
# In the enrich node (S2), fan-out per figure:
for fig in ir.figures:
    call_fp = blake3("vlm", provider.id, provider.version, params,
                     fig.crop_content_hash)
    fig.description = provider_cache.get_or_call(
        call_fp,
        lambda: vlm.describe(fig.crop, grounding=fig.ocr_text),
    )
```

### 5.3 Exécution

- **Macro-DAG** par document (stages, ordre topologique) ; **micro-tâches** pour les fan-outs (par figure en S2, par chunk en S5/S6), dispatchées au pool de workers via la file.
- **Atomicité** : un nœud réussit entièrement ou pas du tout ; un fan-out « complete » quand tous ses sous-appels ont un résultat caché — la reprise ne refait que les manquants.
- **Le cache est le mécanisme de reprise** : pas besoin de durabilité forte d'orchestrateur en v1.
- **GC** : artefacts dont l'empreinte n'est plus référencée par aucune `pipeline_version` active → collectables.
- **Versionner les providers** : `provider_version` (version du modèle servi) entre dans la clé du provider-call cache — un upgrade de VLM buste proprement les vieilles descriptions.

### 5.4 dry_run (le playground)

Même moteur, deux différences : (1) le nœud `index` est remplacé par un **sink éphémère** (aucune écriture en collection réelle/Qdrant) ; (2) le node-cache écrit dans un namespace éphémère, mais le **provider-call cache reste en read-through** (tester est bon marché). Retourne les artefacts intermédiaires (IR, markdown, chunks, preview retrieval). **Parité prod garantie : c'est littéralement le même code de DAG.**

### 5.5 Build vs buy (tranché)

- **Le fingerprint/cache = logique métier, non achetable.** C'est le cœur du produit.
- **Couche d'exécution v1 : runner maison + arq** (le cache fournit reprise/reindex/dry-run). **Migration Temporal** le jour où les jobs longs sur APIs externes instables exigent une durabilité formelle. **Dagster : non** (ses assets nommés ne collent pas au grain par-document + sous-cache par contenu).

---

## 6. Le système de providers

### 6.1 Interfaces (une par capacité)

```python
class OcrProvider(Protocol):
    name: str
    version: str
    runs_on: Literal["cpu", "gpu", "remote"]
    cost_per_page: float                              # 0.0 for local
    def extract(self, img: Image, hint: OcrHint) -> OcrResult: ...


class VlmProvider(Protocol):                           # OpenAI chat-completions shape
    def describe(self, img: Image, grounding: str,
                 schema: JsonSchema | None = None) -> VlmResult: ...


class EmbedProvider(Protocol):
    def embed(self, texts: list[str]) -> EmbedResult: ...   # dense (+ sparse if hybrid-native)


class RerankProvider(Protocol):
    def rerank(self, query: str, docs: list[str]) -> list[float]: ...
```

Chaque **adapter normalise sa sortie vers les slots de l'IR** (`ocr_text`, `description`, `data_table`). Mistral OCR, PaddleOCR local et un VLM OpenAI rendent des formats différents → l'adapter traduit → l'IR reste provider-agnostique.

**Lingua franca : l'API OpenAI-compatible** (vLLM, Ollama, TGI, OpenAI, Mistral, Gemini-compat, OpenRouter…). Local ↔ cloud = `base_url` + `model` dans la config, zéro changement de code.

### 6.2 Résolution en trois niveaux

```
1. LOCALITY GATE (dur)   collection.locality_policy filtre l'ensemble des providers autorisés
2. PROVIDER SELECT       la chaîne choisit le provider (escalade possible)
3. DEVICE FALLBACK       DeviceManager centralisé : tente GPU -> sinon CPU (détection au load)
```

- Le **DeviceManager est centralisé** : une brique déclare `prefers=gpu, can_cpu=true` ; le manager détecte absence GPU/OOM au chargement et replie. Pas de logique device dans les briques.
- L'**ordre de repli est par brique** : `embed -> [gpu, cpu, api]` (CPU viable) ; `vlm -> [gpu, api]` (CPU sauté : qualité/latence inexploitables en volume).
- Le resolver **ne peut jamais** escalader hors de l'allowlist d'une collection — garantie runtime en plus du check statique.

### 6.3 Chaîne d'escalade & contrôle de coût

```python
ocr = ProviderChain(
    [LocalPaddleOcr(),            # 1. try free local CPU first
     MistralOcrApi()],            # 2. escalate to API on low confidence
    escalate_if=lambda r: r.confidence < 0.85,
)
```

Cinq leviers cumulés, du plus rentable au plus fin :
1. **Bypass natif** (S1) : page à couche texte ⇒ jamais d'OCR/VLM.
2. **Gate figure** (S2) : décoratif ⇒ jamais de VLM.
3. **Provider-call cache** : contenu déjà vu ⇒ jamais re-facturé.
4. **Escalade sur confiance** : local d'abord, API seulement où la qualité l'exige.
5. **Budget par job** (plafond de dépense par ingestion) + **batching** des appels API.

### 6.4 Profils de déploiement (même code, config différente)

| Profil | Parse | OCR | VLM | Embed | Rerank | GPU |
|---|---|---|---|---|---|---|
| **Full local GPU** | Docling/MinerU/Marker | olmOCR-2 / PaddleOCR-VL (vLLM) | Qwen2.5-VL-7B (vLLM) | BGE-M3 (TEI) | bge-reranker-v2-m3 (TEI) | oui |
| **CPU + API** | Docling CPU + PyMuPDF | → Mistral OCR API | → API OpenAI-like | BGE-M3 ONNX CPU | bge-reranker ONNX CPU | **non** |
| **Hybride** | local CPU | local léger → API sur échec | API (figures only) | local CPU | local CPU | optionnel |
| **On-premise strict** | local (CPU ou GPU) | local uniquement | local uniquement | local | local | selon dispo |

Réalité CPU assumée : parsing natif + embeddings + rerank tournent bien sur CPU ; OCR-qualité et VLM **doivent** partir en API en mode CPU-only (fallback local Tesseract/PaddleOCR bas de gamme disponible mais non recommandé pour la qualité).

---

## 7. Le système de métadata

### 7.1 Trois rôles, trois formes

| Fonction | Forme | Où | Exemples |
|---|---|---|---|
| **Filtrer** | structuré, indexé | payload Qdrant (sous-ensemble dénormalisé) | `collection_id`, `lang`, `date`, `tags`, `block_type`, `page` |
| **Contextualiser** | langage naturel | tissé dans `embed_text` | titre du doc, breadcrumb, description figure |
| **Afficher / citer / prouver** | fidélité totale | Postgres + object store, **post-fetch** par id après top-k | `raw_text`, `ocr_text`, `description`, `bbox`, `crop_key` |

**Règle d'or : le vecteur reste maigre.** Dans Qdrant : `embed_text` vectorisé + payload filtrable, rien d'autre. Le riche (raw, OCR, descriptions) est récupéré par `chunk_id` en post-fetch Postgres après le top-k.

### 7.2 Trois capacités orthogonales par champ

Chaque champ (système ou métier) porte trois flags indépendants + pondérations :

```sql
-- per-collection field definition (system fields have sensible locked defaults)
metadata_field(
  collection_id, field_name, field_type, required,
  filterable  boolean,   -- promoted to indexed Qdrant payload (exact/range filter)
  lexical     boolean,   -- dedicated BM25 sparse vector (exact/keyword match)
  semantic    boolean,   -- dedicated named dense vector (fuzzy/semantic match)
  weight_lexical  real,
  weight_semantic real
)
```

Matérialisation dans Qdrant (named vectors multiples par point) :

```
point = {
  vectors: {
    content_dense:  emb(embed_text),       # always
    title_dense:    emb(title),            # if title.semantic
    filename_dense: emb(filename),         # if filename.semantic
  },
  sparse: {
    content_bm25:  ...,                     # always
    filename_bm25: ...,                     # if filename.lexical
    project_bm25:  ...,                     # if project.lexical
  },
  payload: { ...filterable fields only... }
}
```

À la requête : la query est embeddée **une fois** (même modèle ⇒ même espace), comparée à chaque named dense vector activé, BM25 sur chaque sparse activé, puis **fusion RRF pondérée** par les poids du schéma — surchargés possibles à la requête. Note UX : sur les champs courts type nom de fichier, le lexical matche généralement mieux que le dense ; l'UI suggère le réglage, l'utilisateur décide. Coût affiché : chaque champ `semantic` = +1 vecteur stocké + 1 passe d'embedding ; chaque `filterable` = +1 index payload (RAM).

### 7.3 Métadata implicite (auto-extraite, jamais fournie par l'utilisateur)

Schéma **système** toujours présent, à côté du schéma métier dynamique. Deux origines :

**File-intrinsèque (S0/S1)** : `filename`, `extension`, `mime_type`, `file_size`, `source_hash`, `source_format` (magic bytes), `author`, `title`, `subject`, `created_at`, `modified_at`, `app_name`, `company` (propriétés core docx/PDF/etc.).

**Pipeline-dérivée** : `page_count`, `language` (+ par bloc), `n_blocks`, `n_tables`, `n_figures`, `has_scanned_pages`, `ocr_used`, `vlm_used`, `parser_backend`, stage fingerprints ; **par bloc** : `page`, `bbox`, `block_type`, `reading_order`, `heading_path`, `token_count`.

Ces champs passent par **le même modèle à trois flags** avec défauts sensés (`filename` → lexical+filterable ; `page`/`language`/`source_format` → filterable ; `heading_path` → embed_text + filterable). L'utilisateur ne les fournit pas, mais peut régler leur comportement de recherche.

`heading_path` est le pont IR ↔ recherche : un champ, les trois rôles (filtre, contexte d'embedding, affichage).

### 7.4 Héritage par scope (zéro duplication)

```
collection -> id, embedding_model, ACL, metadata schema
  document -> source_hash, filename, format, language, dates, user_meta{...}
    section -> heading_path, title, index           (derived from IR hierarchy)
      block -> id, type, page, bbox, order, parent, type_data{...}
        chunk -> block_ids[], raw_text, embed_text, token_count, strategy, prov
```

Une métadata vit à son scope naturel et s'hérite. La **dénormalisation n'existe qu'à la projection vers Qdrant** (sous-ensemble filtrable), snapshot régénéré à chaque indexation, jamais source de vérité.

---

## 8. Modèle de données (Postgres)

```sql
-- SOURCE OF TRUTH
collection(id, name, supported_formats text[], max_file_size, max_pages,
           unknown_field_policy, locality_policy, allowed_providers text[],
           pipeline jsonb, pipeline_version, embedding_model,
           default_search jsonb, created_at)

metadata_field(collection_id, field_name, field_type, required,
               filterable, lexical, semantic, weight_lexical, weight_semantic,
               enum_values text[], is_system boolean)

document(id, collection_id, source_hash, filename, format, language,
         page_count, file_size, user_meta jsonb, implicit_meta jsonb,
         pipeline_version, status, created_at)

block(id, document_id, type, page, bbox float[4], reading_order,
      parent_id, level, text, type_data jsonb)        -- persisted IR

chunk(id, document_id, config_hash, block_ids text[],
      raw_text, embed_text, token_count, strategy, prov jsonb)

-- ENGINE
stage_run(document_id, node_id, fingerprint, output_ref, status,
          started_at, finished_at)                     -- node cache index
provider_call(call_fp primary key, capability, provider_id, provider_version,
              content_hash, result_ref, cost, created_at)  -- provider-call cache
job(id, document_id, collection_id, status, error, budget_spent, created_at)

-- INDEXES THAT MATTER
--   GIN on document.user_meta, document.implicit_meta, block.type_data
--   btree on (collection_id), (document_id), (page)
--   expression indexes on promoted JSONB keys (filterable custom fields)
```

**Object store (MinIO/S3), clés content-addressed :**

| Artefact | Clé |
|---|---|
| Original | `originals/{sha256}` |
| Original→PDF | `derived/{sha256}/pdf` |
| PNG page | `derived/{sha256}/pages/{n}.png` |
| Crop figure | `derived/{sha256}/figures/{block_id}.png` |
| IR sérialisée | `derived/{sha256}/{parse_fp}/ir.json` |
| Vue markdown | `derived/{sha256}/{serialize_fp}/doc.md` |

---

## 9. Retrieval

Pipeline de requête :

```
query
  -> embed once (collection.embedding_model)
  -> Qdrant hybrid search:
       dense on each enabled named vector (content_dense, title_dense, ...)
     + sparse BM25 on each enabled sparse vector (content_bm25, filename_bm25, ...)
     + payload filters (filterable fields, in-graph filtering)
  -> weighted RRF fusion (schema weights, overridable per request)
  -> optional reranker (bge-reranker-v2-m3) on top-N
  -> post-fetch by chunk_id (Postgres): raw_text, ocr_text, description,
     data_table, prov, crop_key, heading_path
  -> response: chunks + provenance + retrieval scores
```

**Features signature** (rendues possibles par la provenance + l'object store) :
- `get_page_screenshot(doc_id, page)` → PNG de la page (fonctionne aussi sur les sources Office via l'original→PDF) ;
- `get_source_pdf(doc_id)` / `get_original(doc_id)` ;
- `locate_passage(chunk_id)` → page + bbox (highlight côté client) ;
- restitution au choix du client : **brut / OCR / description VLM / crop** pour tout bloc figure.

---

## 10. Surfaces

### 10.1 API REST

```
# Collections
POST   /collections                          create (static validation incl. locality)
GET    /collections/{id}/schema              self-documented contract
PUT    /collections/{id}/pipeline            bump pipeline_version
POST   /collections/{id}/reindex             incremental replay (stage cache)

# Ingestion
POST   /collections/{id}/documents           {file, metadata payload}
   -> admission gate (order, fail fast & cheap):
      format in supported_formats?           else 415
      size/pages within limits?              else 413
      payload valid vs metadata_schema?      else 422 (missing required, bad types,
                                                       unknown_field_policy)
      source_hash already ingested (same pipeline_version)?  -> 200 no-op (dedup)
      OK -> 202 + job_id (async)
GET    /jobs/{id}                            progress, per-stage status, cost spent

# Retrieval
POST   /collections/{id}/search              hybrid + filters + weights + rerank flag
GET    /documents/{id}/original | /pdf | /markdown | /ir
GET    /documents/{id}/pages/{n}/screenshot
GET    /chunks/{id}                          full materializations + provenance

# Playground
POST   /playground/run                       dry_run: same engine, ephemeral sink,
                                             returns IR + markdown + chunks + preview search

# Compat
POST   /compat/docling/convert               Docling-compatible shim: accepts same inputs,
                                             returns DoclingDocument JSON (IR mapped via
                                             docling-core types)
```

La validation d'admission est **synchrone et bon marché** ; seul ce qui passe entre dans la pipeline asynchrone — on ne paie jamais un OCR pour un document qui aurait été rejeté.

### 10.2 MCP server (tools)

```
search_collection(query, collection_id, filters, weights)   hybrid + rerank
get_chunk_context(chunk_id)        chunk + heading breadcrumb + neighbor chunks
get_page_screenshot(doc_id, page)  the signature feature
get_source_pdf(doc_id) / get_original(doc_id)
locate_passage(chunk_id)           page + bbox for highlighting
list_collections() / describe_collection(id)   metadata schema -> agents build filters
get_figure(block_id, view="raw"|"ocr"|"description"|"data")
```

### 10.3 UI

- **Playground d'ingestion** (le cœur) : upload échantillon → preview markdown + **overlay des bboxes sur le PDF** → réglage des knobs (backend parse, OCR on/off, VLM description on/off, chart-to-data, stratégie/taille chunking, contextualize, modèle d'embedding, chaînes de providers) → preview des chunks → test de retrieval immédiat → **freeze → Collection**.
- Gestion des collections, éditeur de schéma de métadata (3 flags + poids + required), registre des providers/modèles, monitoring des jobs (statut par stage, coût dépensé, cache hits), explorateur de documents (IR, vues, provenance).
- Contrainte de parité : le playground exécute le **même moteur** en `dry_run`.

---

## 11. Choix technologiques (arrêtés)

| Brique | Choix | Alternatives évaluées / raison |
|---|---|---|
| Langage / API | **Python 3.12 + FastAPI + pydantic v2** | écosystème ML, IR pydantic, `docling-core` réutilisable pour le shim |
| Conversion | **Gotenberg** (seul) | LibreOffice headless brut (fragile), Collabora (fidélité legacy supérieure mais 2e système — non retenu), MS/Aspose (coût) |
| Parse | **Docling** défaut ; **MinerU**, **Marker** routés ; **Tika/Extractous** fallback couverture | benchmarks OmniDocBench/olmOCR-Bench/FinTabNet ; cf. état de l'art |
| OCR local | **olmOCR-2** / **PaddleOCR-VL** (GPU) ; PaddleOCR-v5/Tesseract (CPU bas de gamme) | équilibre précision/débit ; robustesse pipeline sur texte non sémantique |
| OCR API | **Mistral OCR** (défaut, EU) ; Azure DI (option) | gouvernance données + qualité |
| VLM | **Qwen2.5-VL-7B** via vLLM (local) ; toute API OpenAI-like (cloud) | mutualisé description + chart-to-data |
| Embeddings | **BGE-M3** (TEI sur GPU, ONNX sur CPU) ; **Qwen3-Embedding** option qualité | dense+sparse natif en un modèle = hybride simple ; fort FR/multilingue |
| Reranker | **bge-reranker-v2-m3** (TEI/ONNX) | baseline solide ; gte-modernbert si latence critique |
| Classifieur figures | petit **ViT** local (ONNX CPU OK) | router sans payer un VLM par région |
| Vector store | **Qdrant** | filtrage in-graph + named dense multiples + sparse natif + single binary ; pgvector écarté (pas d'hybride natif, post-filtering) ; LanceDB réservé à un futur mode « lib embarquée » |
| SoT | **Postgres 16** (JSONB + GIN) | typé + flexible + transactions + joins ACL |
| Object store | **MinIO** (S3-compatible) | content-addressing, self-host |
| File / workers | **arq** + runner DAG maison | cache = reprise ; Temporal = cible si durabilité formelle requise ; Dagster écarté (grain) |
| Serving local | **vLLM** (VLM/LLM), **TEI** (embed/rerank), **ONNX Runtime** (CPU) | standards de facto, API OpenAI-compatible |
| UI | **React** | — |
| Hashing | **blake3** (fingerprints), sha256 (originaux) | vitesse / convention |

---

## 12. Gouvernance & sécurité

- `locality_policy` par collection : `on_premise_only` ⇒ aucun provider `remote` admissible (check statique à la création **et** garantie runtime du resolver). `external_allowed` ⇒ allowlist explicite de providers.
- Macros Office désactivées (Gotenberg), filtrage des URL sortantes de conversion.
- ACL au niveau collection (extensible document) — jointures Postgres, jamais dans Qdrant seul.
- Budget de dépense par job + comptabilité des coûts par provider_call (visibles dans le monitoring).
- Les caches provider sont partagés mais keyés par contenu — pas de fuite inter-collection de *résultats* sans accès au contenu source correspondant.

---

## 13. Phasage

| Phase | Livrable | Contenu |
|---|---|---|
| **P1 — Fondation** | IR + provenance | S0/S1 : Gotenberg, fork natif/raster, Docling→IR, PNG/page, crops, sérialisation markdown. Postgres + MinIO. |
| **P2 — Moteur** | Stage engine | Fingerprints, node cache, provider-call cache, arq workers, dry_run, atomicité/reprise. |
| **P3 — Enrich** | S2 complet | Classifieur figures, providers OCR/VLM (local + Mistral/OpenAI-like), grounding, chart-to-data, chaînes d'escalade, budget. |
| **P4 — Retrieval** | Chunk→search | S4/S5/S6, BGE-M3, Qdrant multi-vecteurs, fusion RRF pondérée, reranker, post-fetch, métadata 3-flags + implicite. |
| **P5 — Produit** | Collections + API | Contrat Collection, admission gate, endpoints REST, reindex incrémental, jobs/monitoring. |
| **P6 — Surfaces** | UI + MCP | Playground (dry_run + overlay bboxes), admin, MCP tools, shim Docling-compat. |

**Prérequis transverse dès P1 : le harnais d'évaluation** sur la typologie de documents cible (échantillons réels FR : rapports, scans administratifs, tableaux financiers) — métriques parsing (type OmniDocBench), retrieval (Recall@k, nDCG@10, RAGAS). Les benchmarks publics sont directionnels ; chaque knob du produit doit être validable par la mesure interne. C'est aussi le garde-fou des choix par défaut (backends, chunking, overlap, contextual retrieval).

---

## 14. Registre des décisions (ADR condensé)

| # | Décision | Justification clé |
|---|---|---|
| 1 | IR canonique, markdown = vue | le markdown plat ne peut pas porter types/bbox/enrichissements ; provenance structurelle |
| 2 | Wrapper les parsers, pas les réécrire | années-personnes de modèles spécialisés ; la valeur = l'orchestration paramétrable |
| 3 | Gotenberg seul pour la conversion | wrapper ops-grade de LibreOffice + ops PDF gratuites ; Collabora non retenu (2e système) |
| 4 | Tableurs parsés nativement, jamais via PDF | pagination artificielle destructrice ; le PDF sert pagination/screenshots/affichage |
| 5 | Vue plate = structure pure, enrichissements = propriétés IR | fidélité de la vue ; restitution brut/OCR/description au choix du client |
| 6 | Qdrant | hybride natif multi-vecteurs + filtrage in-graph = design center du produit ; pgvector sans hybride natif ; LanceDB réservé au mode embarqué futur |
| 7 | BGE-M3 par défaut | dense+sparse en un modèle ⇒ hybride sans double infra ; fort multilingue/FR |
| 8 | Trois flags métadata orthogonaux (filterable/lexical/semantic) + poids | filtre ≠ match exact ≠ match sémantique ; champs custom ET implicites |
| 9 | Vecteur maigre + post-fetch | index léger, RAM maîtrisée, le riche vit en Postgres/objet |
| 10 | Merkle-DAG + double cache (node / provider-call) | reindex incrémental, reprise, dédup inter-documents, zéro double facturation |
| 11 | Runner maison + arq (v1), Temporal (cible), Dagster écarté | le cache fait la reprise ; grain par-document incompatible Dagster |
| 12 | Providers OpenAI-compatibles, resolver locality→provider→device | interchangeabilité totale local/API ; confidentialité garantie statiquement et au runtime |
| 13 | Collection = contrat (schéma+admission+pipeline+gouvernance) | validation fail-fast avant toute dépense ; auto-documentation du contrat |
| 14 | Playground = même moteur en dry_run | parité test/prod garantie par construction |
| 15 | Embedding model figé par collection | un espace vectoriel = un modèle ; changement ⇒ reindex versionné |
