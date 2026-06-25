---
name: model-cache-concurrency
description: ModelCache per-lib inference-locking policy — which heavy providers MUST serialize inference and which must not
metadata:
  type: project
---

Process-level `ModelCache` (`common/common_libs/providers/model_cache.py`) shares heavy local
models once per worker process. `get_or_load(key, loader)` = double-checked locking (fail closed:
a load failure is NOT cached, propagates); `lock_for(key)` = per-key lock to serialize inference
when a lib isn't concurrency-safe.

**Why:** ProviderRegistry rebuilds providers per job; without this, multi-GB models reloaded per
document. With `WORKER_MAX_JOBS>1`, providers run concurrently in `run_in_executor` threads.

**How to apply (per-lib inference policy — verify on any future edit to these providers):**
- **PaddleOCR** (`ocr/paddle/provider.py`) — NOT thread-safe; `ocr.ocr()` MUST stay wrapped in
  `ModelCache.lock_for(model_key)`. Dropping this lock on the shared engine = real crash/corruption.
  Key includes resolved `lang` (`hint.language or default_lang`), so fr/en get distinct engines.
- **Docling** (`parser/docling/core.py`) — `convert()` not documented thread-safe; serialized via
  `lock_for`. Safe to keep.
- **ViT ONNX** (`classifier/vit_onnx/provider.py`) — `InferenceSession.run()` IS thread-safe;
  intentionally NO lock. Adding one would needlessly kill throughput — flag if someone adds it.

Sharp edge: `get_or_load` fast-path is `is not None`, so a loader returning `None` would never
cache. No current loader returns None; flag any future one that could.
