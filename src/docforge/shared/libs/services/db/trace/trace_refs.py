# ====== Code Summary ======
# TraceRefs — the object-store references to a node's FULL input/output payloads (the full trace tier).
# A plain frozen value object: produced by the worker's payload-store step, consumed by
# ``persist_execution_tree``. Pure: no DB, no object-store I/O.

# ====== Standard Library Imports ======
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TraceRefs:
    """The object-store references to a node's FULL input/output payloads (the full trace tier).

    Produced by the worker's payload-store step (content-hash keys) and consumed by
    ``persist_execution_tree`` to stamp ``input_ref``/``output_ref`` + the ``has_full_*`` flags on the
    node's row. A side left None means that payload was not stored (not captured, or a store miss).

    Attributes:
        input_ref (str | None): Object-store key of the node's full input payload, or None.
        output_ref (str | None): Object-store key of the node's full output payload, or None.
    """

    input_ref: str | None = None
    output_ref: str | None = None


__all__ = ["TraceRefs"]
