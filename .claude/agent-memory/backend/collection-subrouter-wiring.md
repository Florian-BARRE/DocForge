---
name: collection-subrouter-wiring
description: How to add a new per-collection sub-router (3-step registration + discovery overlay pattern)
metadata:
  type: project
---

Adding a per-collection sub-router (e.g. `collections/{id}/metagen`, `/limits`) is a fixed 3-step wiring.

**Why:** the URL structure is centralized in `app/backend/app.py` (routers use only relative leaf
paths); registration is split across 3 files and is easy to half-do.

**How to apply:**
1. Create `app/backend/routers/collections/<name>/{__init__.py, router.py, models.py}`. The
   `__init__.py` exports `router as <name>_router`. Routes use bare leaf paths (`@router.post("/preview")`).
2. `app/backend/routers/__init__.py` — add a labeled `from .collections.<name>.router import router as <name>_router` and add it to `__all__`.
3. `app/backend/app.py` — add `<name>_router` to the `from .routers import (...)` block AND
   `app.include_router(router=<name>_router, prefix=f"{COL}/{{collection_id}}/<name>", dependencies=auth)`.
   `COL = f"{V1}/collections"`, `V1 = "/api/v1"`. `dependencies=auth` = `[Depends(require_principal)]`;
   per-route capability is added inside the router via `Depends(require_capability(Capability.X))`.

Capability convention: a per-collection action that triggers spend or authors config (e.g. the metagen
prompt preview) is gated behind `CONFIG_WRITE`, not a read cap — keeps token spend out of read-only
principals' reach. Search (also spends, on embed) uses `Capability.SEARCH`. See [[metagen-llm-validation-gap]].

Discovery dynamic options for a sub-router's config field: add an entry to the `OVERLAYS` map in
`app/backend/routers/discovery/overlays.py` (keyed by route function name → list of (field_path/prefix,
source) tuples) and a resolver. Collection-scoped sources read `schema_field_dicts(collection.metadata_fields)`
(now carries `origin`). The describer (`config_describer`) stays generic; collection data is injected here only.
