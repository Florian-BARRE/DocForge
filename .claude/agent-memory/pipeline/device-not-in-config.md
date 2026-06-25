---
name: device-not-in-config
description: GPU/device is a deployment env decision, never a per-collection provider config field
metadata:
  type: project
---

Device selection (GPU vs CPU) for LOCAL providers is a DEPLOYMENT decision, never a
per-collection pipeline knob. No provider config exposes a `use_gpu` Pydantic Field.

**Why:** DocForge invariant "DeviceManager centralise GPU/CPU — aucune logique device dans les
briques". A `use_gpu` config Field auto-becomes a misleading (and broken) UI toggle, because
discovery/UI is schema-driven (`describe.py::_params_from_instance` iterates
`model_json_schema().properties`). Removing the Field makes the toggle disappear automatically.

**How to apply (the pattern, identical for all 3 local providers):**
- Provider config (`providers/{parser/docling,ocr/paddle,classifier/vit_onnx}/config.py`):
  - NO `use_gpu` Field. Instead: `_use_gpu: bool = PrivateAttr(default=False)`.
  - `model_config = ConfigDict(extra="ignore")` so a stored config with a STALE `use_gpu` key
    loads without 500 (the key is silently dropped — no migration needed).
  - `merge_defaults(cfg)`: `merged = self.model_copy(); merged._use_gpu = bool(getattr(cfg, "<ENV>", False)); return merged`.
  - `build()`: `return Backend(use_gpu=self._use_gpu)`.
  - The BACKEND keeps its runtime `use_gpu` param (ModelCache key depends on it) — never change that.
- Deployment env flag per provider in `common/base_config/runtime/base_config.py` (+ `.env.example`):
  `DOCLING_USE_GPU`, `PADDLE_USE_GPU`, `VIT_USE_GPU` (all default false).
- `docker-compose.gpu.yml` worker `environment:` sets all three to `true`. CPU stack leaves them false.
- Assembly flow that injects the env: stored/default config → `merge_defaults(cfg)` → `build()`
  (`pipeline/assembly/chain_builders.py`, `describe.py`). `build_default_pipeline` (config/pipeline/pipeline.py)
  instantiates `DoclingConfig()` with NO use_gpu kwarg.

Verify after such a change: `GET /collections/{id}/config/{state,schema}` and `GET /discovery`
emit zero `use_gpu`; a PATCH carrying a stale `use_gpu` returns 200 and round-trips without it.
