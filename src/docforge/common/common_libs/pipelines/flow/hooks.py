# ====== Code Summary ======
# EngineHooks — the no-op I/O seam between the generic flow loop and the environment-specific side
# effects it must perform (node-cache read/write, document lifecycle, gates, one-time prep). The base
# is all-no-op so the engine runs end-to-end with no infrastructure (unit tests + the lab). A
# deployment (the worker) subclasses it to reproduce the real lifecycle, keeping that I/O OUT of the
# nodes. Every per-node hook receives the node's resolved Context (typed input + services), so the
# worker can fingerprint, gate, and persist.

# ====== Local Project Imports ======
from .context import Context, RunContext
from .io import NodeOutput
from .node import Node


class EngineHooks:
    """
    No-op default hooks for the flow loop. Concrete deployments override only what they need.

    - ``prepare``: one-time setup before the root runs.
    - ``should_run`` / ``on_skipped``: a per-node gate.
    - ``before_node`` / ``after_node``: per-node epilogues.
    - ``cache_load`` / ``cache_store``: node-cache read/write (only for nodes with ``CACHED = True``).
    - ``on_error`` / ``mark_failed`` / ``mark_done``: failure + terminal lifecycle.
    """

    async def prepare(self, run: RunContext) -> None:
        """One-time setup before the root node runs."""
        return None

    async def should_run(self, node: Node, ctx: Context, run: RunContext) -> bool:
        """Return False to skip a node (the engine then calls ``on_skipped``)."""
        return True

    async def on_skipped(self, node: Node, ctx: Context, run: RunContext) -> None:
        """Side effect for a node skipped by the gate (e.g. a Postgres-only persistence fallback)."""
        return None

    async def before_node(self, node: Node, ctx: Context, run: RunContext) -> None:
        """Run immediately before a node executes."""
        return None

    async def after_node(self, node: Node, ctx: Context, output: NodeOutput, run: RunContext) -> None:
        """Run immediately after a node executes successfully."""
        return None

    async def cache_load(self, node: Node, ctx: Context, run: RunContext) -> NodeOutput | None:
        """Load a node's cached output. Return the output on a hit, None on a miss."""
        return None

    async def cache_store(self, node: Node, ctx: Context, output: NodeOutput, run: RunContext) -> None:
        """Persist a freshly-run node's output under its fingerprint."""
        return None

    async def on_error(self, node: Node, exc: Exception, run: RunContext) -> None:
        """Run when a node fails (e.g. mark its node-cache row failed)."""
        return None

    async def mark_failed(self, run: RunContext) -> None:
        """Flip the run to its failed terminal state."""
        return None

    async def mark_done(self, run: RunContext) -> None:
        """Flip the run to its done terminal state after the root succeeded."""
        return None


__all__ = ["EngineHooks"]
