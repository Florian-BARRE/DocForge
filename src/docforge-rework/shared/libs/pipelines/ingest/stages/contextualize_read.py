# ====== Code Summary ======
# ContextualizeReader — reads the contextualize stack back out of an ingestion blob (the inverse of
# the contextualize segment builder). It walks the root nodes in order; a simple method (doc_meta,
# breadcrumb, sliding) is one contextualize node read verbatim, while the llm method is the
# externalised prep(llm) → ForEach(generic-llm chain [+ keep_raw]) → apply(llm_apply) topology. An
# llm prep STARTS a position: the reader finds the ForEach whose ``over`` reads that prep, walks the
# generic-``llm`` chain out of the loop body (the keep_raw terminal is family ``contextualize``, so it
# is naturally excluded), and captures the prep's config (which carries the on_error stage knob). The
# paired llm_apply is skipped. What the reader captures, the segment builder re-emits verbatim, so a
# view → apply → view round-trip is stable for a 1-step and a multi-step llm stack alike.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import FromNode
from shared_libs.pipelines.build.blob import (
    ActionNodeBlob,
    ForEachNodeBlob,
    GroupNodeBlob,
    NodeBlob,
)

# ====== Local Project Imports ======
from .chain_walk import ChainWalker
from .models import ChainSpec, ChainStep, StackMethod

_LLM = "llm"


class ContextualizeReader:
    """Static reader deriving the ordered contextualize stack (llm topology included) from a blob."""

    logger = loggerplusplus.bind(identifier="ContextualizeReader")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ContextualizeReader is a static-only class and cannot be instantiated.")

    @classmethod
    def stack(cls, ordered: list[NodeBlob]) -> list[StackMethod]:
        """
        Derive the ordered contextualize methods from the root nodes (root order = application order).

        Args:
            ordered (list[NodeBlob]): The topologically ordered root nodes of the blob.

        Returns:
            list[StackMethod]: The stack methods in order — an llm method carries its derived chain.
        """
        methods: list[StackMethod] = []
        for node in ordered:
            if not isinstance(node, ActionNodeBlob) or node.family != "contextualize":
                continue
            # The apply is the back half of an llm position — its prep already emitted the method.
            if node.kind == "llm_apply":
                continue
            if node.kind == _LLM:
                methods.append(cls.__llm_method(ordered, node))
            else:
                methods.append(StackMethod(kind=node.kind, config=dict(node.config)))
        return methods

    @classmethod
    def __llm_method(cls, ordered: list[NodeBlob], prep: ActionNodeBlob) -> StackMethod:
        """An llm position: the prep config + the generic-llm chain walked out of its ForEach body."""
        loop = cls.__loop(ordered, prep.id)
        return StackMethod(kind=_LLM, config=dict(prep.config), chain=cls.__chain(loop))

    @classmethod
    def __loop(cls, ordered: list[NodeBlob], prep_id: str) -> ForEachNodeBlob | None:
        """The ForEach whose ``over`` reads the prep node's prompts (the position's per-prompt loop)."""
        return next(
            (
                node
                for node in ordered
                if isinstance(node, ForEachNodeBlob)
                and isinstance(node.over, FromNode)
                and node.over.node_id == prep_id
            ),
            None,
        )

    @classmethod
    def __chain(cls, loop: ForEachNodeBlob | None) -> ChainSpec:
        """The generic-llm chain walked out of the ForEach body (keep_raw is naturally excluded).

        A missing loop / empty ladder yields the stock 1-step llm default so a re-emit stays valid.
        """
        if loop is None:
            return cls.__default()
        body: GroupNodeBlob = loop.body
        nodes = {
            node.id: node
            for node in body.nodes
            if isinstance(node, ActionNodeBlob) and node.family == _LLM
        }
        if not nodes:
            return cls.__default()
        head = ChainWalker.head(body.transitions, nodes, {_LLM})
        steps = ChainWalker.walk(body.transitions, nodes, head, {_LLM})
        return ChainSpec(family=_LLM, steps=steps) if steps else cls.__default()

    @staticmethod
    def __default() -> ChainSpec:
        """The stock 1-step llm chain (its endpoint lives in its own step config)."""
        return ChainSpec(family=_LLM, steps=[ChainStep(kind="openai_compatible")])


__all__ = ["ContextualizeReader"]
