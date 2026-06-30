# ====== Code Summary ======
# MetagenResult dataclass — the record produced by the metagen stage's assemble node. Kept in its own
# module so the result type is importable without pulling in the node's provider/cache dependencies.
# It carries the same chunks (with chunk-scope derived_meta filled), the document-scope generated
# values, the count of generated values, the estimated LLM spend, and one chain trace per scope-group
# for lineage flushing by the orchestrator.

# ====== Standard Library Imports ======
from dataclasses import dataclass, field
from typing import Any

# ====== Internal Project Imports ======
from common_libs.domain import Chunk


@dataclass(slots=True)
class MetagenResult:
    """
    Output record of the metagen stage.

    Attributes:
        chunks (list[Chunk]): The same chunk objects, with chunk-scope generated values written into
            each ``chunk.derived_meta`` (mutated in place by the chunk-scope node).
        doc_fields (dict[str, Any]): Document-scope generated values ``{field_name: value}`` merged
            into ``doc_meta`` by the assemble node (user-supplied values win on conflict).
        n_generated (int): Count of generated values written (chunk-scope + document-scope).
        est_cost_usd (float): Estimated LLM spend for this document's metagen calls.
        chain_traces (list[Any]): One ChainTrace per scope-group, capturing the provider attempts.
    """

    chunks: list[Chunk]
    doc_fields: dict[str, Any] = field(default_factory=dict)
    n_generated: int = 0
    est_cost_usd: float = 0.0
    chain_traces: list[Any] = field(default_factory=list)


__all__ = ["MetagenResult"]
