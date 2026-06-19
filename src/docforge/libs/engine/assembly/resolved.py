# ====== Code Summary ======
# ResolvedStages dataclass — concrete pipeline stages resolved from a PipelineConfig
# for a single run.  Extracted from registry.py so it can be imported independently
# without pulling in ProviderRegistry's full dependency tree.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from libs.capabilities.chain import Chain
    from libs.engine.stages.s2_enrich import S2EnrichStage
    from libs.engine.stages.s4_chunk import S4ChunkStage
    from libs.engine.stages.s5_contextualize import S5ContextualizeStage


@dataclass(slots=True)
class ResolvedStages:
    """
    Concrete pipeline stages resolved from a PipelineConfig for a single run.

    S0/S6 are handled outside this struct (S0 is constant; S6 owns a live Qdrant connection
    managed by the worker/app, not the registry).

    Attributes:
        parse_chain (Chain[ParserProvider, DocumentIR]): Ordered parser chain for S1.
        s2 (S2EnrichStage): Enrichment stage — always present (pipeline is fixed S0→S6).
        s4 (S4ChunkStage): Chunking stage — always present.
        s5 (S5ContextualizeStage): Contextualization stage — always present.
    """

    parse_chain: Chain[Any, Any]
    s2: S2EnrichStage
    s4: S4ChunkStage
    s5: S5ContextualizeStage

    @property
    def parser(self) -> Any:
        """Backward-compat shim — returns the FIRST provider in the parse chain."""
        return self.parse_chain.providers[0] if self.parse_chain.providers else None
