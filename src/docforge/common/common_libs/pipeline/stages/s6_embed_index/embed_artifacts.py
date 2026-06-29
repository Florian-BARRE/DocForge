# ====== Code Summary ======
# S6EmbedArtifacts — the typed hand-off between the embed phase and the index phase of S6. It
# carries everything the Qdrant upsert needs that the embed phase computed: the chunks actually
# indexed (parents excluded), the content dense/sparse vectors, the per-field dense/sparse vectors,
# and the vector plan. Extracted so the native EmbedStep can produce it and the native IndexStep can
# consume it via the pipeline context, keeping the embed->index data flow explicit and typed.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from common_libs.domain.ir.chunk import Chunk


@dataclass(slots=True)
class S6EmbedArtifacts:
    """
    Vectors + plan produced by the S6 embed phase, consumed by the S6 index phase.

    Attributes:
        index_chunks (list[Chunk]): Chunks that are indexed in Qdrant (hierarchical parents excluded).
        content_dense (list): Per-chunk content dense vectors (1:1 with ``index_chunks``; None where degraded).
        content_sparse (list | None): Per-chunk content sparse vectors, or None when no sparse was produced.
        field_dense (dict[str, list]): Per metadata field name -> per-chunk dense vectors.
        field_sparse (dict[str, list]): Per metadata field name -> per-chunk sparse vectors.
        plan (Any): The vector plan (named dense/sparse vectors) from ``FieldIndexHelpers.derive_vector_plan``.
    """

    index_chunks: "list[Chunk]"
    content_dense: "list[list[float] | None]"
    content_sparse: "list[dict[int, float] | None] | None"
    field_dense: "dict[str, list[list[float] | None]]"
    field_sparse: "dict[str, list[dict[int, float] | None]]"
    plan: Any


__all__ = ["S6EmbedArtifacts"]
