# MinerU2.5-Pro VLM layout-parsing sidecar (`mineru_server`)

A self-contained model-host micro-service that parses a PDF with **MinerU2.5-Pro** (SOTA document
parser, OmniDocBench 95.69) and returns the **shared DocForge sidecar contract** — the same wire shape
`paddle_server`'s `/vl-parse` returns, so a single DocForge IR mapper serves both. The DocForge
`parser/mineru` node is a pure httpx client of this service.

> **GPU-ONLY.** MinerU2.5-Pro's VLM backend requires CUDA (min 8 GB VRAM). The prod GPU is a Tesla
> V100 (sm_70) → the GPU image pins torch **cu126** (cu129/cu130 drop Volta). The `cpu` build variant
> exists only to import-test the wiring; it cannot actually parse, and `/health` reports UNHEALTHY on a
> CPU host (`MINERU_REQUIRE_GPU`, on by default).

## HTTP API

| Route | Method | Body | Returns |
|---|---|---|---|
| `/health` | GET | — | `{status, ready, detail, device}` — 503 (`"status":"unhealthy"`) when no CUDA GPU is visible and `MINERU_REQUIRE_GPU`. |
| `/parse` | POST | raw PDF bytes (`Content-Type: application/pdf`) | `{pages:[{page_index, image_width, image_height, blocks:[{label, bbox, reading_order, text?|html?|latex?}]}], n_pages, engine}` |

Blocks are reading-ordered; `bbox` is in the page's `0–1000` normalization space (`image_width` /
`image_height` = 1000). Tables arrive as HTML in `html`, formulas as LaTeX in `latex`.

The service is built on the shared `src/model_server_core` library: the core owns the app skeleton
(config base, lifespan with fail-fast config validation, gzip, `GET /health`, typed error handler,
request guards, device probe, logging bootstrap); this folder only holds what is MinerU's own.

## Errors

An unexpected exception answers **HTTP 500** with a generic typed body and a correlation id; the
exception itself (type, message, traceback) is only in the server log, under the same id:

```json
{"detail": {"error": "Internal server error. The details were logged.", "correlation_id": "<uuid hex>"}}
```

The id is also sent as the `X-Correlation-ID` response header. The deliberate answers are unchanged:
`413` (body over `MINERU_MAX_BODY_BYTES`), `422` (empty or undecodable PDF) and `503` + `Retry-After`
(predict lock saturated).

## How it is built

- **`entrypoint.py`** — zero logic: `ServerEntrypoint(MineruServer(MineruServerConfig))`.
- **`config_loader.py`** — `MineruServerConfig(ServerConfig)`: the `MINERU_*` env vars.
- **`backend/mineru_server.py`** — `MineruServer(ModelServer)`: title, model service, the `/parse`
  route, and the GPU gate behind `/health`.
- **`backend/routers/parse/`** — `ParseRoutes`: `POST /parse`, bound to the service and the core
  request guards.
- **`libs/mineru/normalizer.py`** — PURE, fully unit-tested (`tests/test_normalizer.py`): converts
  MinerU's flat `content_list.json` (`type` / `bbox` 0–1000 / `page_idx` / `text_level` / `table_body`
  HTML / equation `text` LaTeX / `image_caption` / `list_items`) into the shared per-page contract. No
  MinerU/torch/CUDA import — runs offline.
- **`libs/mineru/engine.py`** — the ONE **GPU-only, GPU-UNTESTED** seam: calls MinerU's `do_parse`
  (backend `MINERU_BACKEND`, default `vlm-transformers`) and reads the `*_content_list.json` it writes.
  Validate on first GPU deploy (see the module docstring's checklist).
- **`libs/mineru/service.py`** — `MineruService(ModelService)`: serializes every parse behind an
  `asyncio.Lock` (503 on lock-wait timeout), runs the engine off the event loop, normalizes the result.
- **`libs/mineru/torch_cuda_detector.py`** — the torch GPU check injected into the core `DeviceProbe`.

## Build

```bash
# GPU (production, CUDA 12.6):
docker build --build-arg TORCH_VARIANT=gpu -f src/mineru_server/Dockerfile -t docforge-mineru-server:gpu src
# CPU (wiring build-test only — cannot parse):
docker build -f src/mineru_server/Dockerfile -t docforge-mineru-server:cpu src
```

In compose it is an **opt-in** service under the `mineru` profile (never started by `--profile full`);
the GPU override grants it `gpus: all`. See `compose/README.md`.

## Test / lint (offline)

```bash
cd src/mineru_server
uv run ruff check . && uv run ruff format --check .
uv run pytest tests -q
```

All tests are offline (the normalizer over a synthetic `content_list.json`, the routes over a stubbed
engine) — no GPU required. `tests/characterization/` pins the OpenAPI document and the `/parse` wire
goldens.
