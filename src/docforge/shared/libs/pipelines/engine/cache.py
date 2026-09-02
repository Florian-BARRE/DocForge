# ====== Code Summary ======
# The engine's CACHE SEAM — a tiny, storage-agnostic contract the engine calls at a cacheable
# root-stage boundary, plus the global ENGINE_CACHE_EPOCH constant folded into every cache key.
# The engine knows NOTHING about S3/Postgres, key composition or (de)serialisation: it only holds a
# reference to an object satisfying this Protocol on its RunContext and calls before()/after(). The
# real implementation (all I/O) lives worker-side (StageCacheHook), so the pure engine stays pure.

# ====== Standard Library Imports ======
from typing import Protocol, runtime_checkable

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeInput, NodeOutput

# The engine-wide cache generation. It is folded into EVERY cache key, so bumping it invalidates the
# entire artifact cache at once — the blunt defence against an engine-wide change (a serialisation or
# IR-shape shift) that could make an old cached artifact wrong even though no single node's
# CACHE_VERSION moved. A per-node ``CACHE_VERSION`` handles a single node's semantic drift; this
# handles everything below the nodes. Bump it (as a reviewer rule) on any cross-cutting engine change
# that could alter what a cached stage output means.
ENGINE_CACHE_EPOCH = "1"


@runtime_checkable
class CacheHook(Protocol):
    """
    The run-scoped stage-cache seam the engine calls at a cacheable root-stage boundary.

    The engine calls ``before`` right after resolving a cacheable root node's input: a returned
    output is a HIT (the node's ``run`` is skipped and the cached output flows on); ``None`` is a
    MISS (the node runs, then the engine calls ``after`` with the produced output to store it). The
    implementation owns key computation, lookup, (de)serialisation and all store I/O — the engine
    never learns any of it.
    """

    async def before(self, node_id: str, resolved_input: NodeInput) -> NodeOutput | None:
        """Return the cached output for this node (a HIT) or None to run it (a MISS)."""
        ...

    async def after(self, node_id: str, resolved_input: NodeInput, output: NodeOutput) -> None:
        """Store the output a just-run cacheable node produced (best-effort; never raises)."""
        ...


__all__ = ["CacheHook", "ENGINE_CACHE_EPOCH"]
