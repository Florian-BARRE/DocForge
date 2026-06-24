# ====== Code Summary ======
# S6Result dataclass — output of the S6 embedding and indexing stage.
# Extracted from s6_embed_index.py to keep the result model separately importable
# without pulling in S6EmbedIndexStage's heavy dependencies (Qdrant, embed chains).

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from common_libs.domain.ir.models import ChainTrace


@dataclass(slots=True)
class S6Result:
    """
    Output of the S6 embedding and indexing stage.

    Attributes:
        n_embedded (int): Number of chunks passed through the embedding model (content).
        n_upserted_qdrant (int): Number of points upserted to Qdrant.
        n_inserted_postgres (int): Number of chunk rows inserted into Postgres.
        collection_name (str): Qdrant collection name used for the upsert.
        n_field_vectors (int): Number of per-field named vectors materialized.
        chain_traces (list[ChainTrace]): Per-batch embed chain traces; the engine
            appends them onto ``DocumentIR.chain_traces`` for full lineage.
    """

    n_embedded: int
    n_upserted_qdrant: int
    n_inserted_postgres: int
    collection_name: str
    n_field_vectors: int = 0
    chain_traces: list[ChainTrace] = field(default_factory=list)
