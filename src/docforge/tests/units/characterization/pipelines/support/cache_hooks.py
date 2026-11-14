# ====== Code Summary ======
# CacheHook doubles for the engine's cache-seam characterization: one that misses and records its calls,
# one whose lookup raises, one whose store raises. The engine must degrade a raising hook to a miss /
# an uncached success, never to a failed node.

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeInput, NodeOutput


class RecordingCacheHook:
    """A hook that always misses and logs every call as ``("before"|"after", node_id)``."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def before(self, node_id: str, resolved_input: NodeInput) -> NodeOutput | None:
        self.calls.append(("before", node_id))
        return None

    async def after(self, node_id: str, resolved_input: NodeInput, output: NodeOutput) -> None:
        self.calls.append(("after", node_id))


class RaisingLookupHook(RecordingCacheHook):
    """A hook whose ``before`` raises (the engine must treat it as a miss)."""

    async def before(self, node_id: str, resolved_input: NodeInput) -> NodeOutput | None:
        await super().before(node_id, resolved_input)
        raise RuntimeError("lookup exploded")


class RaisingStoreHook(RecordingCacheHook):
    """A hook whose ``after`` raises (the engine must keep the run's success)."""

    async def after(self, node_id: str, resolved_input: NodeInput, output: NodeOutput) -> None:
        await super().after(node_id, resolved_input, output)
        raise RuntimeError("store exploded")


class ServingCacheHook(RecordingCacheHook):
    """A hook that HITs: serves a fixed output for every node it is asked about."""

    def __init__(self, served: NodeOutput) -> None:
        super().__init__()
        self._served = served

    async def before(self, node_id: str, resolved_input: NodeInput) -> NodeOutput | None:
        await super().before(node_id, resolved_input)
        return self._served
