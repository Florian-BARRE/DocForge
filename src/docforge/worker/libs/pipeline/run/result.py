# ====== Code Summary ======
# IngestRunResult — the aggregated output of one ingest run on the node engine, in the shape the arq
# task reads to build its job summary (status + per-stage Merkle fingerprints + cache-hit flags +
# the chunk / embed result tallies). It is assembled by the IngestRunner from the per-run hooks
# accumulators + the captured stage outputs, replacing the legacy orchestrator EngineResult.

# ====== Standard Library Imports ======
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class IngestRunResult:
    """
    Aggregated output of an ingest run on the node engine.

    Attributes:
        status (str): The root report status (``ok`` / ``failed`` / ...).
        stage_fingerprints (dict[str, str]): NODE_CACHED stage Merkle fingerprints, keyed by stage key.
        from_cache (dict[str, bool]): Per-NODE_CACHED-stage cache-hit flags, keyed by stage key.
        chunk_result (Any): The chunk stage S4Result (per-kind tallies); None on a failed run.
        embed_result (Any): The embed/index result (n_upserted_qdrant); None when no collection.
        stage_outputs (dict[str, Any]): Every captured stage output, keyed by stage key.
    """

    status: str
    stage_fingerprints: dict[str, str] = field(default_factory=dict)
    from_cache: dict[str, bool] = field(default_factory=dict)
    chunk_result: Any = None
    embed_result: Any = None
    stage_outputs: dict[str, Any] = field(default_factory=dict)


__all__ = ["IngestRunResult"]
