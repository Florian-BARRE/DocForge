# ====== Code Summary ======
# EngineHooks — the injection seam between the generic engine loop and the environment-specific I/O
# it must perform (node-cache read/write, document lifecycle, gates, one-time prep). The base is an
# all-no-op default so the engine runs end-to-end with no infrastructure (used by unit tests and the
# standalone lab). A deployment (the worker) subclasses it to reproduce the real lifecycle, keeping
# all that I/O OUT of the nodes themselves.
#
# The middleware applies to EVERY node (a NODE_CACHED stage is cached as one unit; a gate can veto a
# whole stage), so the per-node hooks receive the node's resolved Context (its typed Input + services)
# — the worker needs it to compute the cache fingerprint (upstream fingerprints + chain signatures),
# to read a stage's input on a skip, and to persist a stage's output.

# ====== Internal Project Imports ======
from ..base import AbstractNode, ContextBase, NodeOutput, RunContext


class EngineHooks:
    """
    No-op default hooks for the engine loop.

    Every method is a no-op (or permissive default) so the engine is fully functional standalone.
    Concrete deployments override only the methods they need:

    - ``prepare``: one-time setup before the root runs (e.g. download original bytes).
    - ``should_run`` / ``on_skipped``: a per-node gate (e.g. skip the embed/index stage without a
      collection, persisting chunks to Postgres only).
    - ``before_node`` / ``after_node``: per-node epilogues (e.g. mark 'running', persist artefacts).
    - ``cache_load`` / ``cache_store``: node-cache read/write keyed by the node fingerprint (only
      consulted for ``CachePolicy.NODE_CACHED`` nodes).
    - ``on_error`` / ``mark_failed`` / ``mark_done``: failure + terminal lifecycle.
    """

    async def prepare(self, run: RunContext) -> None:
        """One-time setup before the root node runs."""
        return None

    async def should_run(self, node: AbstractNode, ctx: ContextBase, run: RunContext) -> bool:
        """Return False to skip a node (the engine then calls ``on_skipped``)."""
        return True

    async def on_skipped(self, node: AbstractNode, ctx: ContextBase, run: RunContext) -> None:
        """Side effect for a node skipped by the gate (e.g. a Postgres-only persistence fallback)."""
        return None

    async def before_node(self, node: AbstractNode, ctx: ContextBase, run: RunContext) -> None:
        """Run immediately before a node executes (its children, or a leaf body)."""
        return None

    async def after_node(
        self, node: AbstractNode, ctx: ContextBase, output: NodeOutput, run: RunContext
    ) -> None:
        """Run immediately after a node executes successfully."""
        return None

    async def cache_load(
        self, node: AbstractNode, ctx: ContextBase, run: RunContext
    ) -> NodeOutput | None:
        """Load a node's cached output. Return the output on a hit, None on a miss."""
        return None

    async def cache_store(
        self, node: AbstractNode, ctx: ContextBase, output: NodeOutput, run: RunContext
    ) -> None:
        """Persist a freshly-run node's output under its fingerprint."""
        return None

    async def on_error(self, node: AbstractNode, exc: Exception, run: RunContext) -> None:
        """Run when a node fails, before its error policy is applied (e.g. mark node failed)."""
        return None

    async def mark_failed(self, run: RunContext) -> None:
        """Flip the run to its failed terminal state."""
        return None

    async def mark_done(self, run: RunContext) -> None:
        """Flip the run to its done terminal state after every node succeeded."""
        return None


__all__ = ["EngineHooks"]
