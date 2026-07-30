# ====== Code Summary ======
# ContextualizeStack — the one place the contextualize stack's node LAYOUT is computed, shared by the
# segment builder (which emits the nodes/transitions) and the assembler (which threads the chunks
# spine). It turns the ordered StackMethod list into a list of StackPosition: one richer descriptor
# per stack slot carrying the ids and (for the llm method) the externalised prep→ForEach→apply shape.
# A simple method (doc_meta, breadcrumb, sliding) is a single node whose head == tail. The llm method
# is a prep (control-in + chunks-in) → a per-prompt ForEach loop → an apply (control-out + chunks-out);
# its ``output`` anchors downstream on the apply, and it carries the generic-llm chain + the on_error
# policy its ForEach body needs. Ids stay unique per method occurrence (ctx_llm, ctx_llm_2, …), so the
# stack may repeat the llm method — two situating passes is legitimate, not a wiring error.

# ====== Standard Library Imports ======
from dataclasses import dataclass

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import Binding, FromNode
from shared_libs.pipelines.ingest.nodes.contextualize.base import OnChunkError

# ====== Local Project Imports ======
from .models import ChainSpec, ChainStep, StackMethod
from .state import PipelineState

# Human ids for the stock stack nodes, so the default stack keeps its historical ids byte-for-byte.
_CTX_IDS = {
    "doc_meta": "ctx_meta",
    "breadcrumb": "ctx_breadcrumb",
    "sliding": "ctx_sliding",
    "llm": "ctx_llm",
}
_LLM_KIND = "llm"


@dataclass(frozen=True)
class StackPosition:
    """One slot of the contextualize stack — its ids, downstream anchor and (for llm) its topology.

    A simple method is a single node: ``head_id == tail_id`` and there is no loop/apply/chain. The
    llm method externalises into ``head_id`` (the prep — control-in + chunks-in), ``loop_id`` (the
    per-prompt ForEach) and ``tail_id``/``apply_id`` (the apply — control-out + chunks-out); it carries
    the generic-llm ``chain`` its body runs and the ``on_error`` policy that decides the keep_raw
    terminal. ``output`` is the SINGLE source of truth for the slot's downstream anchor (always the
    tail's ``chunks``), so the assembler threads the spine identically for both shapes.

    Attributes:
        method (StackMethod): The stack method this position realises.
        head_id (str): The node an incoming control edge routes into (chunks-in bound here).
        tail_id (str): The node the next slot is wired from (chunks-out read here).
        output (Binding): The slot's downstream anchor — ``FromNode(tail_id, "chunks")``.
        loop_id (str | None): The ForEach id (llm only).
        apply_id (str | None): The apply id (llm only; equals ``tail_id``).
        chain (ChainSpec | None): The generic-llm chain the ForEach body runs (llm only).
        on_error (OnChunkError | None): The keep_raw / fail policy shaping the body (llm only).
    """

    method: StackMethod
    head_id: str
    tail_id: str
    output: Binding
    loop_id: str | None = None
    apply_id: str | None = None
    chain: ChainSpec | None = None
    on_error: OnChunkError | None = None

    @property
    def is_llm(self) -> bool:
        """Whether this slot externalises into a prep → ForEach(llm chain) → apply topology."""
        return self.chain is not None


class ContextualizeStack:
    """Static computer of the contextualize stack layout (positions) shared by builder + assembler."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ContextualizeStack is a static-only class and cannot be instantiated.")

    @classmethod
    def positions(cls, state: PipelineState) -> list[StackPosition]:
        """
        Lay out the ordered stack as StackPositions, ids unique per method occurrence.

        Args:
            state (PipelineState): The canonical state whose ``stack`` to lay out.

        Returns:
            list[StackPosition]: One position per method, in application order.
        """
        used: list[str] = []
        positions: list[StackPosition] = []
        for method in state.stack:
            base = _CTX_IDS.get(method.kind, f"ctx_{method.kind}")
            candidate, suffix = base, 2
            while candidate in used:
                candidate = f"{base}_{suffix}"
                suffix += 1
            used.append(candidate)
            positions.append(cls.__position(method, candidate))
        return positions

    @classmethod
    def __position(cls, method: StackMethod, base: str) -> StackPosition:
        """Build one position — a single node for a simple method, the externalised shape for llm."""
        # 1. A simple method is one node: head == tail, its chunks output anchors the next slot.
        if method.kind != _LLM_KIND:
            return StackPosition(
                method=method,
                head_id=base,
                tail_id=base,
                output=FromNode(node_id=base, field_name="chunks"),
            )
        # 2. The llm method externalises into prep(base) → loop → apply; the loop/apply ids derive
        #    from the (unique) base, so repeating the method keeps them distinct too.
        loop_id, apply_id = f"{base}_loop", f"{base}_apply"
        return StackPosition(
            method=method,
            head_id=base,
            tail_id=apply_id,
            output=FromNode(node_id=apply_id, field_name="chunks"),
            loop_id=loop_id,
            apply_id=apply_id,
            chain=method.chain or cls.__default_chain(),
            on_error=cls.__on_error(method.config),
        )

    @staticmethod
    def __on_error(config: dict) -> OnChunkError:
        """The slot's fail policy read off the method config (defaults to the fail-soft keep_raw)."""
        raw = config.get("on_error")
        return OnChunkError(raw) if raw else OnChunkError.KEEP_RAW

    @staticmethod
    def __default_chain() -> ChainSpec:
        """The stock 1-step llm chain (inherits its endpoint from its own step config)."""
        return ChainSpec(family="llm", steps=[ChainStep(kind="openai_compatible")])


__all__ = ["StackPosition", "ContextualizeStack"]
