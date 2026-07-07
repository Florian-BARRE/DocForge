---
name: extra-ignore-provider-field-removal
description: Sanctioned pattern to remove a config field while keeping stored configs loadable — ConfigDict(extra="ignore") + dead-block/duplicate cleanup; review checklist
metadata:
  type: project
---

Removing a now-dead Pydantic config field (search.rerank.top_n, search.retrieve.grouping.group_by,
classifier.vit_onnx.use_gpu) without breaking stored configs is done with **`model_config =
ConfigDict(extra="ignore")`** on the model: the dropped key is silently ignored at load (NOT 422).
Validated good — do NOT flag as a backward-compat gap.

**Why:** per-collection pipeline configs are stored in the `collection.pipeline` JSONB column; old rows
may still carry the removed key. `extra="ignore"` drops it on parse; `extra="forbid"`/default would 422
every legacy collection. Unknown *provider ids* are still rejected (the discriminated-union dispatch is
unchanged) — only unknown *scalar keys* are dropped.

**How to apply (review checklist when a field is removed):**
- Confirm `ConfigDict(extra="ignore")` is on the exact model the key lived in (RerankConfig,
  GroupingConfig, VitOnnxConfig — not a parent).
- grep that NOTHING still reads the removed field (engine, validators, post-processor, frontend
  types/state). Comments/docstrings/test-assertions mentioning the name are fine.
- A test should assert both: field gone from `Model.model_fields` AND a stored dict carrying it loads
  (not raises) with the attr absent on the instance.
- If the removal also deletes a duplicate/dead validation block, verify the SURVIVING check still covers
  the intent. See [[locality_empty_chain_nameerror]].

Related: [[deployment_knob_privateattr]] (use_gpu removal via PrivateAttr), [[secret_roundtrip]].
