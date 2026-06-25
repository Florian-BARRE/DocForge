---
name: worker-torch-variants
description: Worker image cpu/gpu torch wheel selection — how the common deps contract steers transitive docling torch to the right wheel index
metadata:
  type: project
---

The worker image picks its torch wheel variant via two mutually-exclusive extras in
`src/docforge/common/pyproject.toml`: `cpu` (committed default) and `gpu` (opt-in).

**Why it works:** docling pulls torch + torchvision *transitively* (via docling-ibm-models),
but `[tool.uv.sources]` index routing only applies to DIRECT deps. So `cpu`/`gpu` each
re-declare `torch` and `torchvision` as direct deps, and `[tool.uv.sources]` routes BOTH to
`pytorch-cpu` (download.pytorch.org/whl/cpu) or `pytorch-cu124` (whl/cu124) per extra.
`[tool.uv] conflicts` makes cpu/gpu mutually exclusive. Mirrors `src/bge_server` exactly.

**Resolved versions (lock):** cpu → torch 2.12.1+cpu / torchvision 0.27.1+cpu (no nvidia-* CUDA
libs). gpu → torch 2.6.0+cu124 / torchvision 0.21.0+cu124 + nvidia-cuda-* (linux/x86_64 markers).
Note the gpu path pins an OLDER torch (2.6.0) — that's the latest torch the cu124 index publishes.

**How to apply:**
- Worker Dockerfile: `uv sync --frozen --no-dev --extra worker --extra "${TORCH_VARIANT}"`,
  ARG TORCH_VARIANT=cpu. GPU build: `--build-arg TORCH_VARIANT=gpu`.
- App image uses plain `uv sync` (no worker/cpu/gpu) — pulls ZERO torch/docling/cuda. Unaffected.
- VALIDATION on a non-linux host: `uv sync --extra gpu --dry-run` FAILS with "no wheel for current
  platform" — this is a host install-check artifact, NOT a lock error. The +cu124 linux/amd64 wheels
  ARE in the lock (they install in the container). Validate gpu resolution with `uv export` instead
  of `--dry-run` (export is resolution-only, skips the host install check).
- cpu+gpu together is correctly rejected by uv at sync time (conflict declaration).

Pre-existing unrelated warning: `tool.uv.dev-dependencies` is deprecated (use `dependency-groups.dev`).
Left as-is — not in scope. See [[backend-worker-libs-architecture]] for the broader image split.
