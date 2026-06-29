# ====== Code Summary ======
# S5bResult dataclass — output of the S5b metagen stage. Kept in its own module so the result type
# is importable without pulling in S5bMetagenStage's provider/cache dependencies (mirrors S5Result).

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from common_libs.domain.ir.chunk import Chunk


@dataclass(slots=True)
class S5bResult:
    """
    Output of the S5b metagen stage.

    Attributes:
        chunks (list[Chunk]): The same chunk objects, with chunk-scope generated values written
            into each ``chunk.derived_meta`` (mutated in place).
        doc_fields (dict): Document-scope generated values ``{field_name: value}``; merged into
            ``doc_meta`` by the orchestrator (user-supplied values win on conflict).
        n_generated (int): Count of generated values written (chunk-scope + document-scope).
        est_cost_usd (float): Estimated LLM spend for this document's metagen calls.
        chain_traces (list): One ChainTrace per scope-group, capturing the provider attempts.
    """

    chunks: list[Chunk]
    doc_fields: dict[str, Any] = field(default_factory=dict)
    n_generated: int = 0
    est_cost_usd: float = 0.0
    chain_traces: list[Any] = field(default_factory=list)


__all__ = ["S5bResult"]
