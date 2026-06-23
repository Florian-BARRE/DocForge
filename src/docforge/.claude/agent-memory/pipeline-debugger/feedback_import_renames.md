---
name: feedback-import-renames-after-libs-reorg
description: How to diagnose and fix broken imports left over from the libs/ restructuring — renamed classes and moved modules
metadata:
  type: feedback
---

After the `libs/` restructuring (2026-06-19), callers were left importing old names/paths that no longer exist. Two patterns recur:

**Pattern A — Renamed class:** A caller imports `SemanticParams` but the class was renamed to `SemanticConfig` (in `libs/pipeline/stages/s4_chunk/config/semantic.py`). Fix: update the import in the caller to use an alias (`SemanticConfig as SemanticParams`) so the internal `isinstance()` guard still works without logic changes.

**Pattern B — Renamed module file:** A caller imports from `libs.search.hybrid.hybrid_search_models` but the file was renamed to `models.py`. Fix: update the import path to `libs.search.hybrid.models`.

**Why:** The `libs/` restructuring (phase map in `.claude/rules/phases.md`) moved and renamed many modules. Docker __pycache__ hid the errors in production; pytest reveals them because it triggers a fresh import chain.

**How to apply:** When a pytest collection fails with `ImportError` or `ModuleNotFoundError`, always:
1. Check what actually exists in the target directory (`ls`) before guessing the fix.
2. For missing class names — search the config/ or strategies/ subdir for `Semantic*` or similar.
3. For missing module files — the correct name is almost always the short form (`models.py`, `helpers.py`) rather than the verbose old form (`hybrid_search_models.py`).
