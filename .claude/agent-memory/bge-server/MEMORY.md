# BGE-Server Agent — Memory Index

Component: **`src/bge_server/`** — standalone LOCAL model host serving BGE-M3 dense+sparse
**embedding** AND BGE-reranker-v2-m3 **rerank** over the TEI HTTP contract. Rule-compliant FastAPI
micro-service: `entrypoint.py`, `config_loader.py` (BgeServerConfig), `libs/bge_models/` (service +
device resolver), `backend/` (routers, context, lifespan). Device policy configurable via `BGE_DEVICE`
(auto/cuda/cpu). Models loaded once at startup via FlagEmbedding (torch), CPU by default.

- [model-host-contract](model-host-contract.md) — endpoints, env vars, why it replaced off-the-shelf TEI, and how docforge consumes it
