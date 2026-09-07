# dots.ocr per-element layout VLM sidecar (`dots_ocr_server`)

A self-contained model-host micro-service that parses a PDF with **dots.ocr** (`rednote-hilab/dots.ocr`,
a compact ~3B per-element layout VLM, **MIT**) and returns the **shared DocForge sidecar contract** —
the same wire shape `mineru_server`'s `/parse` and `paddle_server`'s `/vl-parse` return, so a single
DocForge IR mapper style serves them all. The DocForge `parser/dots_ocr` node is a pure httpx client of
this service.

> **GPU-ONLY.** dots.ocr is served by **vLLM** (≥0.11, which ships the dots.ocr integration) and
> requires CUDA. The prod GPU is a Tesla V100 (sm_70) → the GPU image routes torch to the **cu126**
> wheel index (cu129/cu130 drop Volta). The `cpu` build variant exists only to import-test the wiring
> (vLLM is not even installed on it); it cannot parse, and `/health` reports UNHEALTHY on a CPU host
> (`DOTS_OCR_REQUIRE_GPU`, on by default).

## HTTP API

| Route | Method | Body | Returns |
|---|---|---|---|
| `/health` | GET | — | `{status, ready, detail}` — 503 when no CUDA GPU is visible and `DOTS_OCR_REQUIRE_GPU`. |
| `/parse` | POST | raw PDF bytes (`Content-Type: application/pdf`) | `{pages:[{page_index, image_width, image_height, blocks:[{label, bbox, reading_order, text?|html?|latex?}]}], n_pages, engine}` |

Blocks are reading-ordered; `bbox` is in the **rendered page image's PIXEL space** (top-left origin),
and `image_width`/`image_height` are that rendered image's dims — the DocForge mapper divides one by
the other to recover `[0, 1]`. Tables arrive as HTML in `html`, formulas as LaTeX in `latex`; a
`Picture` block carries no text (its crop is filled by the DocForge `figure_render` stage).

## How it is built (the two halves)

- **`libs/dots_ocr/normalizer.py`** — PURE, fully unit-tested (`tests/test_normalizer.py`): converts
  dots.ocr's per-page JSON output (a list of `{category, bbox pixels, text, reading_order}` elements,
  optionally fenced in ```json) into the shared per-page contract — category→label, Table→`html`,
  Formula→`latex`, Picture→empty text, else→`text`; a missing/malformed bbox degrades to the full page,
  and a HIGH fallback rate is **warned** (a schema-drift tripwire, since the engine is GPU-untested). No
  vllm/torch/CUDA import — runs offline.
- **`libs/dots_ocr/engine.py`** — the ONE **GPU-only, GPU-UNTESTED** seam: renders each PDF page to an
  image (pypdfium2, capturing its px dims), sends `image + prompt_layout_all_en` to the dots.ocr model
  via vLLM's in-process `LLM.chat`, and returns each page's raw JSON string. Validate on first GPU
  deploy (see the module docstring's checklist).
- **`libs/dots_ocr/service.py`** — validates the PDF (422), serializes every parse behind an
  `asyncio.Lock` (503 on lock-wait timeout), runs the engine off the event loop, normalizes the result.

## Design note — why in-process vLLM (self-contained)

dots.ocr is officially served by vLLM's OpenAI-compatible server. To keep this a **single
self-contained container** (matching the compose ripple: `gpus: all` + a model-cache volume on THIS
service), the engine loads the weights **in-process** via vLLM's offline `LLM` engine and calls
`LLM.chat` per page, rather than managing a separate `vllm serve` subprocess. One process, lazy load,
lock-serialized — the same discipline as `mineru_server`.

## Build

```bash
# GPU (production, CUDA 12.6):
docker build --build-arg TORCH_VARIANT=gpu -f src/dots_ocr_server/Dockerfile -t docforge-dots-ocr-server:gpu src
# CPU (wiring build-test only — cannot parse, no vllm):
docker build -f src/dots_ocr_server/Dockerfile -t docforge-dots-ocr-server:cpu src
```

In compose it is an **opt-in** service under the `dots_ocr` profile (never started by `--profile
full`); the GPU override grants it `gpus: all`. See `compose/README.md`.

## Test / lint (offline)

```bash
cd src/dots_ocr_server
uv run ruff check . && uv run ruff format --check .
uv run pytest tests -q
```

All tests are offline (the normalizer over a synthetic dots.ocr page output) — no GPU required.

## GPU first-deploy validation (could NOT be tested on the CPU dev VM)

- Confirm `DOTS_OCR_MODEL_PATH` (default `rednote-hilab/dots.ocr`) loads under vLLM ≥0.11 with
  `trust_remote_code=True` on the target GPU. **NOTE:** the task brief spelled the repo `dots.mocr`;
  the actual HuggingFace repo is `dots.ocr` — override `DOTS_OCR_MODEL_PATH` if the brief was right.
- Confirm the layout prompt `_PROMPT_LAYOUT_ALL_EN` (in `engine.py`) matches the current dots.ocr model
  card verbatim — a prompt mismatch degrades output silently (watch the normalizer's bbox-fallback
  warning in the logs).
- Confirm `LLM.chat(...)` with an `image_url` data-URI message returns the per-page JSON string in
  `outputs[i].outputs[0].text` for the installed vLLM version.
- Confirm the cu126 torch that vLLM pins still ships **sm_70** kernels for the V100 (vLLM 0.11 resolved
  torch 2.9.0+cu126 here); if not, pin an older vLLM/torch that does.
- Confirm `DOTS_OCR_RENDER_DPI` (default 200) gives the model enough resolution on dense pages.
