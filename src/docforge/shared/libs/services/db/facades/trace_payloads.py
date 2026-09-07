# ====== Code Summary ======
# The transfer object crossing the trace-payload façade boundary: TracePayloadRead is the outcome of
# a single full-payload fetch — whether the addressed stage-event row exists, whether a full raw
# payload is actually available for the requested slot, and (when it is and fits the read cap) the
# parsed payload plus its stored size. A plain dataclass so the router maps it to 200 / typed 404
# without knowing the store.

# ====== Standard Library Imports ======
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class TracePayloadRead:
    """
    The outcome of a single trace full-payload fetch (one node, one slot).

    Attributes:
        found (bool): The addressed stage-event row exists under the job (False → the id is unknown).
        has_full (bool): A full raw payload was stored for the requested slot AND is still available
            (a row that only ever carried a shape summary — or whose payload was GC'd — reads False).
        stage (str): The node's stage id (a display label; empty when the row was not found).
        node_path (str | None): The node's materialized tree path (None for a legacy row / not found).
        payload (Any): The node's full raw payload (arbitrary JSON), or None when truncated/unavailable.
        truncated (bool): The stored object exceeded the read cap, so ``payload`` was NOT downloaded.
        size_bytes (int): The stored object's size in bytes (0 when unavailable).
    """

    found: bool
    has_full: bool = False
    stage: str = ""
    node_path: str | None = None
    payload: Any = None
    truncated: bool = False
    size_bytes: int = 0


__all__ = ["TracePayloadRead"]
