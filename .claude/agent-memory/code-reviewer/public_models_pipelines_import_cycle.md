---
name: public_models_pipelines_import_cycle
description: public_models ↔ pipelines.base is now a bidirectional import cycle resolved only by __init__ ordering — a layering inversion to watch on any public_models edit
metadata:
  type: project
---

# public_models ↔ pipelines.base import cycle (introduced P5a)

`shared/libs/public_models/endpoint.py` (`OpenAICompatConfig`) imports `NodeConfig` from
`shared_libs.pipelines.base.io`. But `pipelines/base/foreach.py` imports `Artifact` from
`public_models`, and `pipelines/base/__init__.py` imports `.foreach`. So the two layers now depend on
each other **bidirectionally** — a real layering inversion (public_models is declared the bottom layer
in architecture.md, yet now reaches up into pipelines).

**Why it works today:** `public_models/__init__.py` imports `Artifact` at line 1, `.endpoint` at
line ~47. When endpoint triggers `pipelines.base.__init__` → `foreach` → `from public_models import
Artifact`, Artifact is already bound. Reorder those __init__ lines (endpoint before Artifact) and it
deadlocks with a partial-import ImportError.

**Also note:** importing the *leaf* module `pipelines.base.io` still executes
`pipelines/base/__init__.py` (node/group/foreach/graph/...). It does NOT pull the node-FAMILY registry
(`auto_import` lives in `nodes/` + `ingest/`), so the functional intent (public_models importable
without the registry) holds — but the "not the pipelines.base package" wording in endpoint.py's Code
Summary is mechanically inaccurate.

**How to apply:** on any edit to `public_models/__init__.py` ordering, or anything moving a
`NodeConfig` subclass into public_models, flag the fragility. The clean fix is to move `NodeConfig`
itself down into public_models (both live in the bottom layer) or have `OpenAICompatConfig` not
subclass `NodeConfig`. Related: [[layer_dag]].
