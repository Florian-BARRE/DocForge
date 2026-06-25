# ====== Code Summary ======
# ModelCache — a process-level cache for heavy local ML models (Docling, PaddleOCR, ONNX…).
#
# The ProviderRegistry rebuilds fresh provider instances on every pipeline run (per job) for
# per-collection config isolation.  Heavy local-model providers would otherwise reload their
# multi-GB weights on every document.  This cache loads each model EXACTLY ONCE per worker
# process and shares it across all provider instances/jobs, keyed by the model-DETERMINING
# params only (device, model id/path, language) — never the full per-collection config.
#
# Memory trade-off: cached models stay resident for the lifetime of the worker process
# (Docling + Paddle + ONNX can each be GBs).  This is intentional for a long-lived worker —
# we trade RAM/VRAM for not paying the ~15s load cost on every document.
#
# Thread-safety: providers run inside ``run_in_executor`` threads and WORKER_MAX_JOBS may be
# >1, so access is concurrent.  Loads are serialized per key (exactly-once) via a per-key
# ``threading.Lock``.  The same per-key lock is exposed via ``lock_for`` so callers whose
# library is NOT safe for concurrent inference can serialize inference on the shared instance.

# ====== Standard Library Imports ======
from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus


class ModelCache:
    """
    Static process-level cache mapping a model-key to a single loaded heavy model.

    Usage::

        model = ModelCache.get_or_load(("docling", use_gpu), self._build_converter)
        # for a library that is not safe to call concurrently:
        with ModelCache.lock_for(("paddle", lang, use_gpu)):
            result = model.ocr(arr)

    The key must capture every parameter that changes the loaded weights (device, model id /
    path, language) and NOTHING else — two configs that differ only in non-model fields share
    one entry, while a CPU vs GPU (or fr vs en) config gets distinct entries.
    """

    logger = loggerplusplus.bind(identifier="ModelCache")

    # Loaded models, keyed by their model-determining params (hashable tuple).
    _models: dict[Any, Any] = {}
    # One lock per key — serializes the load and (optionally) inference for that model.
    _key_locks: dict[Any, threading.Lock] = {}
    # Guards creation of the per-key locks themselves (the registry mutation).
    _registry_lock: threading.Lock = threading.Lock()

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        """Block instantiation — this is a static-only cache."""
        raise TypeError("ModelCache is a static-only class and cannot be instantiated.")

    @classmethod
    def lock_for(cls, key: Any) -> threading.Lock:
        """
        Return the per-key lock, creating it on first use.

        Callers whose underlying library is not safe for concurrent inference can wrap their
        inference call in ``with ModelCache.lock_for(key):`` to serialize it on the shared model.

        Args:
            key (Any): Hashable model-determining key (same one passed to ``get_or_load``).

        Returns:
            threading.Lock: The lock dedicated to this key.
        """
        # 1. Look up (or create) the lock under the registry guard so two threads never
        #    create two different locks for the same key.
        with cls._registry_lock:
            lock = cls._key_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                cls._key_locks[key] = lock
            return lock

    @classmethod
    def get_or_load(cls, key: Any, loader: Callable[[], Any]) -> Any:
        """
        Return the cached model for ``key``, invoking ``loader`` exactly once on a miss.

        The load runs under the per-key lock so concurrent threads requesting the same model
        block until the first finishes loading, then all reuse the single instance.  A loader
        failure is NOT cached and propagates to every waiting caller (fail-closed — consistent
        with the provider raise-on-failure contract).

        Args:
            key (Any): Hashable model-determining key (device, model id/path, language…).
            loader (Callable[[], Any]): Zero-arg callable that loads and returns the heavy model.

        Returns:
            Any: The shared, process-cached model instance.

        Raises:
            Exception: Re-raises whatever ``loader`` raises (the entry is left unset).
        """
        # 1. Fast path: already loaded — no locking needed (dict reads are atomic in CPython).
        cached = cls._models.get(key)
        if cached is not None:
            return cached

        # 2. Slow path: serialize the load on the per-key lock (load-exactly-once).
        with cls.lock_for(key):
            # Re-check inside the lock: another thread may have loaded it while we waited.
            cached = cls._models.get(key)
            if cached is not None:
                return cached

            cls.logger.info(f"ModelCache MISS for key={key!r} - loading model (once per process)...")
            model = loader()  # a failure here propagates and is intentionally NOT cached
            cls._models[key] = model
            cls.logger.info(f"ModelCache LOADED key={key!r}")
            return model

    @classmethod
    def clear(cls) -> None:
        """
        Drop all cached models and their locks (test-only helper).

        Not used in production — models are meant to live for the worker's lifetime.  Exposed
        so unit tests can isolate cache state between cases.
        """
        with cls._registry_lock:
            cls._models.clear()
            cls._key_locks.clear()


# ------------------- Public API ------------------- #
__all__ = ["ModelCache"]
