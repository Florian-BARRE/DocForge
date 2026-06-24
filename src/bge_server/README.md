# BGE-M3 dense + sparse embedding micro-service

A small, reliable, **fully local** embedding service that serves **BAAI/bge-m3** producing
both **dense** (1024-dim) and **native multilingual sparse** (lexical weights) vectors.

It speaks the **same HTTP contract as HuggingFace TEI** (`/embed`, `/embed_sparse`, `/health`),
so DocForge drives it with the **existing `tei` embed provider — no new provider code**. Unlike
a real TEI server (which only exposes BGE-M3 in dense `cls` pooling), this service exposes
BGE-M3's sparse head, enabling true multilingual hybrid search locally.

## Why this and not TEI / Infinity
- **TEI** `/embed_sparse` is SPLADE-only → it returns HTTP 424 for BGE-M3 (cls pooling) → dense only.
- **SPLADE** models are English-centric → poor multilingual sparse.
- **BGE-M3 via FlagEmbedding** = one multilingual model, dense + sparse in one pass, API we control.

## Endpoints (TEI-compatible)
| Method | Path | Body | Response |
|---|---|---|---|
| GET  | `/health` | — | `{"status":"ok","model":"BAAI/bge-m3"}` |
| POST | `/embed` | `{"inputs": ["…"], "normalize": true, "truncate": true}` | `[[float, …], …]` (dense) |
| POST | `/embed_sparse` | `{"inputs": ["…"], "truncate": true}` | `[[{"index": int, "value": float}, …], …]` (sparse) |

## Build
```bash
# From the repo root, with src/ as the build context:
docker build -f src/bge_server/Dockerfile -t bge-m3-server:latest src
```

## docker-compose service (add when your compose is stable)
```yaml
  bge-m3-embed:
    build:
      context: src
      dockerfile: bge_server/Dockerfile
    image: bge-m3-server:latest
    volumes:
      - bge_m3_models:/models        # HuggingFace cache — weights persist across restarts
    networks:
      - docforge_net
    restart: unless-stopped
    # Optional dev access:
    # ports: ["10028:80"]

# under top-level volumes:
#   bge_m3_models:
```

## Wire it into a DocForge collection
Point the collection's embed provider at this service via the existing `tei` provider and enable
sparse (multilingual hybrid):

```json
{
  "pipeline": {
    "embed": {
      "chain": [
        { "id": "tei", "base_url": "http://bge-m3-embed:80", "embed_sparse": true }
      ]
    }
  }
}
```

Notes:
- Set `base_url` explicitly to `http://bge-m3-embed:80` — do NOT rely on `TEI_BASE_URL`
  (that points at the dense-only TEI server).
- `semantic` metadata fields → dense vector; `lexical` fields → sparse vector — routed
  automatically from the single embed call (see `metadata_indexer`).
- Changing the embed config flags documents for reindex with an exact cause; reindexing
  re-runs only S4→S6 (parse/OCR are served from the node cache).

## Config / env
| Env | Default | Purpose |
|---|---|---|
| `BGE_M3_MODEL` | `BAAI/bge-m3` | Model id to load |
| `BGE_M3_FP16` | `false` | Use fp16 (GPU only) |
| `BGE_M3_MAX_LENGTH` | `8192` | Max input tokens |
