# ====== Code Summary ======
# The context carried through a single engine run. It holds the pipeline's external run input and
# an optional progress callback the engine fires at each node's START/END. It is the seam where
# run-scoped concerns (cache hooks, collection id…) will plug in later without changing the engine
# signature.

# ====== Standard Library Imports ======
from dataclasses import dataclass
from typing import Any

# ====== Local Project Imports ======
from .progress import ProgressCallback


@dataclass(slots=True)
class RunContext:
    """
    Run-scoped state for one engine execution.

    Attributes:
        run_input (dict[str, Any]): The pipeline's external input, addressable by ``FromRunInput``.
        progress_callback (ProgressCallback | None): Called at each node's START/END, if provided.
    """

    run_input: dict[str, Any]
    progress_callback: ProgressCallback | None = None


__all__ = ["RunContext"]
