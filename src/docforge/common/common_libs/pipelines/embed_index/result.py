# ====== Code Summary ======
# EmbedIndexResult — the typed output payload of the embed_index stage. It carries the per-run counts
# (chunks embedded, points upserted to Qdrant, chunk rows persisted to Postgres), the target
# collection, the number of per-field named vectors materialised, and the per-batch embed chain traces
# the orchestrator flushes onto the document IR for lineage.

# ====== Standard Library Imports ======
from dataclasses import dataclass, field

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import ChainTrace


@dataclass(slots=True)
class EmbedIndexResult:
    """
    Output of the embed_index stage (embed + Qdrant upsert + Postgres persist).

    Attributes:
        n_embedded (int): Number of chunks passed through the embedding model (content).
        n_upserted_qdrant (int): Number of points upserted to Qdrant.
        n_inserted_postgres (int): Number of chunk rows persisted into Postgres.
        collection_name (str | None): Qdrant collection the points were upserted into (None when the
            stage ran with no target collection — the Postgres-only path).
        n_field_vectors (int): Number of per-field named vectors materialised.
        chain_traces (list[ChainTrace]): Per-batch embed chain traces; the orchestrator appends
            them onto ``DocumentIR.chain_traces`` for full lineage.
    """

    n_embedded: int
    n_upserted_qdrant: int
    n_inserted_postgres: int
    collection_name: str | None
    n_field_vectors: int = 0
    chain_traces: list[ChainTrace] = field(default_factory=list)


__all__ = ["EmbedIndexResult"]
