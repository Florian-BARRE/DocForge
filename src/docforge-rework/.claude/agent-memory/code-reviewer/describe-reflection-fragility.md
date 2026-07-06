---
name: describe-reflection-fragility
description: AbstractNode.describe() reads field_info.annotation.__name__ and crashes on union/optional slot types; palette builds all node cards so one bad slot breaks the whole palette
metadata:
  type: project
---

`ActionNode.describe()` (`shared/libs/pipelines/base/node.py`) builds `IoSlot.artefact_type` via `field_info.annotation.__name__` for every Consumes/Produces field.

- A slot typed `X | None` (or any `A | B` union) is a `types.UnionType` with **no `__name__`** → `AttributeError` (confirmed by test).
- A slot typed `list[X]` yields `__name__ == "list"`, silently losing the element type.

**Why it matters:** `NodeRegistry.catalog` / `PipelineCatalog.palette` call `describe()` for EVERY registered node. One node with an optional/union slot raises during palette construction and takes down the whole palette endpoint. Today all node slots are plain artefact classes so it doesn't fire — it's a latent landmine.

**How to apply:** flag any node that declares an optional or generic I/O slot until `describe()` resolves annotation names robustly (handle `UnionType`, generic aliases). Note also `IoSlot.required` is always the default `True` — describe() never derives optionality from the pydantic field. Related: [[pipeline-engine-edge-selection]].
