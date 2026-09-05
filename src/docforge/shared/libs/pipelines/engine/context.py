# ====== Code Summary ======
# The context carried through a single engine run. It holds the pipeline's external run input and
# an optional progress callback the engine fires at each node's START/END. It is the seam where
# run-scoped concerns (cache hooks, collection id…) will plug in later without changing the engine
# signature.

# ====== Standard Library Imports ======
from dataclasses import dataclass
from typing import Any

# ====== Local Project Imports ======
from .cache import CacheHook
from .progress import ProgressCallback


@dataclass(slots=True)
class RunContext:
    """
    Run-scoped state for one engine execution.

    Attributes:
        run_input (dict[str, Any]): The pipeline's external input, addressable by ``FromRunInput``.
        progress_callback (ProgressCallback | None): Called at each node's START/END, if provided.
        cache_hook (CacheHook | None): The worker-provided stage-cache seam. When present, the engine
            consults it at a cacheable root node's boundary (a HIT skips the node). None (the default)
            makes the engine run exactly as if no cache existed — no behaviour change whatsoever.
        callback_error (BaseException | None): Set by the engine when the progress callback itself
            raised (caller-owned control flow — e.g. the worker's cooperative-cancel guard aborting
            at a stage boundary). ``execute``'s record-not-crash net re-raises this UNCHANGED instead
            of converting it into a recorded FAILED run, so the caller's abort semantics stay intact.
    """

    run_input: dict[str, Any]
    progress_callback: ProgressCallback | None = None
    cache_hook: CacheHook | None = None
    callback_error: BaseException | None = None


__all__ = ["RunContext"]
