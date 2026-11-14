# ====== Code Summary ======
# Progress-event emission for the engine: fires the run's caller-owned progress callback for a node
# event. Shared by the walker (every child's START/END) and the foreach runner (its own START, which
# carries the item total). It marks a callback that raised on the RunContext so ``execute``'s
# record-not-crash net re-raises it unchanged instead of recording a FAILED run.

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import AbstractNode, NodeExecutionRecord

# ====== Local Project Imports ======
from .context import RunContext
from .progress import ProgressEvent, ProgressPhase


class ProgressEmitter:
    """Static-only helper: fire the run's progress callback for one node event."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ProgressEmitter is a static-only class and cannot be instantiated.")

    @staticmethod
    async def emit(
        context: RunContext,
        phase: ProgressPhase,
        node: AbstractNode,
        record: NodeExecutionRecord | None = None,
        total_items: int | None = None,
    ) -> None:
        """Fire the run's progress callback for a node event, if one is registered.

        The progress callback is CALLER-OWNED control flow: the worker wraps it with a cooperative-
        cancel guard that RAISES at a stage boundary to abort the run. Such an exception must reach
        the caller UNCHANGED (so it can mark the job CANCELLED, not FAILED) — it is never a node
        failure. Record which exception came from the callback so ``execute``'s record-not-crash net
        re-raises it rather than converting it into a FAILED record. (``asyncio.CancelledError`` is a
        BaseException and already bypasses that net; only an ``Exception``-typed abort needs marking.)

        Args:
            context (RunContext): The run-scoped context holding the callback.
            phase (ProgressPhase): START or END.
            node (AbstractNode): The node the event is about.
            record (NodeExecutionRecord | None): The node's record (END events).
            total_items (int | None): The fan-out width (a ForEach's START event).
        """
        if context.progress_callback is None:
            return
        try:
            await context.progress_callback(
                ProgressEvent(
                    phase=phase,
                    node_id=node.id,
                    kind=node.KIND,
                    record=record,
                    total_items=total_items,
                )
            )
        except Exception as exc:
            context.callback_error = exc
            raise


__all__ = ["ProgressEmitter"]
