---
name: deployment-knob-privateattr
description: Sanctioned pattern for removing a per-collection provider knob (e.g. use_gpu) without breaking stored configs — PrivateAttr + env in merge_defaults + extra="ignore"
metadata:
  type: project
---

# Deployment-only provider knob — the sanctioned removal pattern

When a provider config field is actually a DEPLOYMENT decision (device/GPU, infra),
not a per-collection knob, it must NOT be a Pydantic field. The validated pattern
(used to strip `use_gpu` from docling/paddle/vit_onnx configs, 2026-06-25):

- Field removed; replaced by `_x: T = PrivateAttr(default=...)` (e.g. `_use_gpu`).
- `model_config = ConfigDict(extra="ignore")` so an old stored blob still carrying
  the removed key (`{id, use_gpu:true}` after the `_compat` flatten of `{id,params:{...}}`)
  loads without raising — the key is simply dropped.
- `merge_defaults(cfg)` does `merged = self.model_copy(); merged._x = bool(getattr(cfg, "ENV_FLAG", False))`.
  `model_copy()` carries `__pydantic_private__`; reassign on the copy is correct v2 usage.
- `build()` reads `self._x` and passes it to the runtime Backend/Provider (which KEEPS
  the kwarg — the runtime layer legitimately owns the device flag).
- Env flag lives in `BaseRuntimeConfig` (default false) + `services/docforge/.env.example`;
  `docker-compose.gpu.yml` sets it true. Three flags: DOCLING_USE_GPU / PADDLE_USE_GPU / VIT_USE_GPU.

**Why this is coherent with the DeviceManager invariant:** DeviceManager isn't built at
config-assembly time, so a deployment env flag is the legitimate device signal at that layer.
It does NOT bypass `DeviceManager.resolve()` — same "deployment decides device" principle.

## What to verify when reviewing this pattern (the real risks)
- `extra="ignore"` on EVERY affected config model (not just one). grep `ConfigDict(extra`.
- No `extra="forbid"` anywhere in `config/pipeline/` stage configs or `PipelineConfig`
  that would choke before the union member's `extra="ignore"` applies.
- PrivateAttr → excluded from `model_fields`/JSON schema, so it CANNOT resurface in
  `model_dump`/config_state/discovery (`describe._params_from_instance` is schema-driven).
- ModelCache key tuples must include the device flag (`("docling.converter", use_gpu)` etc.)
  so GPU/CPU variants don't collide.
- Runtime backend/provider tests that pass `use_gpu=` directly are UNAFFECTED (that layer keeps it).
- Nice-to-have test: assert a stored `{id, <removed_key>:true}` blob round-trips (loads,
  key dropped, absent from model_dump) — locks the backward-compat guarantee.

## Frontend twin (same changeset)
Provider conditional params are FLAT on the wire: `{id, param1, param2}`, NO nested `params`.
`PickerValue = { id: string; [param: string]: unknown }`. Pickers read params via
`(value as Record<string, unknown>)[p.name]`, never `.params`. A nested `{id, params:{}}`
serialization breaks BOTH read and write of every conditional param. When reviewing pickers,
grep frontend for `.params` on values — should find zero value accesses.
