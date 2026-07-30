# ====== Code Summary ======
# MetagenReader — reads the two metagen stages back out of an ingestion blob (the inverse of the
# metagen segment builder). Each metagen stage is a prep action → ForEach(structgen chain [+ skip]) →
# apply action, so this reader finds the scope's PREP node (by family/kind), then the ForEach whose
# ``over`` points at that prep, then walks the structgen ladder out of the loop body into a ChainSpec.
# The prep node's config doubles as the stage config (the assembler reads on_error / max_concurrency
# off it), so the stage compiler recovers everything it needs from the prep alone. A missing stage
# yields the stock 1-step structgen default so a re-enable starts from a valid provider.

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
from .models import ChainStep
from .state import ChainSpec

_STRUCTGEN = "structgen"


class MetagenReader:
    """Static reader deriving a metagen stage's prep node and structgen chain from a blob."""

    logger = loggerplusplus.bind(identifier="MetagenReader")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("MetagenReader is a static-only class and cannot be instantiated.")

    @classmethod
    def prep(cls, ordered: list[NodeBlob], prep_kind: str) -> ActionNodeBlob | None:
        """The metagen PREP action of a scope (kind ``chunk_prep`` / ``document_prep``), or None."""
        return next(
            (
                node
                for node in ordered
                if isinstance(node, ActionNodeBlob)
                and node.family == "metagen"
                and node.kind == prep_kind
            ),
            None,
        )

    @classmethod
    def chain(cls, ordered: list[NodeBlob], prep: ActionNodeBlob | None) -> ChainSpec:
        """The scope's structgen chain, walked out of the ForEach body its prep feeds.

        A missing stage / loop / empty ladder yields the stock 1-step structgen default so a
        re-enable starts from a valid provider.
        """
        loop = cls.__loop(ordered, prep.id) if prep is not None else None
        if loop is None:
            return cls.__default()
        body: GroupNodeBlob = loop.body
        nodes = {
            node.id: node
            for node in body.nodes
            if isinstance(node, ActionNodeBlob) and node.family == _STRUCTGEN
        }
        if not nodes:
            return cls.__default()
        head = ChainWalker.head(body.transitions, nodes, {_STRUCTGEN})
        steps = ChainWalker.walk(body.transitions, nodes, head, {_STRUCTGEN})
        return ChainSpec(family=_STRUCTGEN, steps=steps) if steps else cls.__default()

    @classmethod
    def __loop(cls, ordered: list[NodeBlob], prep_id: str) -> ForEachNodeBlob | None:
        """The ForEach whose ``over`` reads the prep node's requests (the scope's per-request loop)."""
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

    @staticmethod
    def __default() -> ChainSpec:
        """The stock 1-step structgen chain (inherits the per-request endpoint)."""
        return ChainSpec(family=_STRUCTGEN, steps=[ChainStep(kind="openai_compatible")])


__all__ = ["MetagenReader"]
