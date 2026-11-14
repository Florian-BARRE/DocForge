# ====== Code Summary ======
# Explorer chunk-toggle models: the single and bulk searchability patches and their results.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class ChunkEnabledPatch(BaseModel):
    """
    The desired searchability state for one chunk (its enabled_override).

    Attributes:
        enabled (bool): True to make the chunk searchable, False to hide it.
    """

    enabled: bool = Field(description="True to make the chunk searchable, False to hide it.")


class BulkChunkEnabledPatch(BaseModel):
    """
    Toggle several chunks' searchability to the same state in one call.

    Attributes:
        chunk_ids (list[str]): The chunks to toggle (at least one).
        enabled (bool): The state to apply to every listed chunk.
    """

    chunk_ids: list[str] = Field(min_length=1, description="The chunks to toggle (at least one).")
    enabled: bool = Field(description="The state to apply to every listed chunk.")


class ChunkEnabledResult(BaseModel):
    """
    The outcome of toggling one chunk's searchability.

    Attributes:
        chunk_id (str): The toggled chunk.
        enabled (bool): The recomputed EFFECTIVE state (override ?? role default).
        reindex_required (bool): True when a never-embedded chunk was enabled — needs a re-embed.
        search_sync_pending (bool): Postgres committed the toggle but the Qdrant payload flip failed —
            the search store is stale until a re-run/backfill reconciles it. Meaningful on the
            single-chunk route; in a bulk response the request-level flag is authoritative.
        search_sync_error (str | None): The Qdrant failure message when ``search_sync_pending``.
    """

    chunk_id: str = Field(description="The toggled chunk's UUID.")
    enabled: bool = Field(description="The recomputed effective searchability state.")
    reindex_required: bool = Field(
        description="True when a never-embedded chunk was enabled — needs a deferred re-embed."
    )
    search_sync_pending: bool = Field(
        default=False,
        description="Postgres committed but the Qdrant sync failed — stale until reconciled.",
    )
    search_sync_error: str | None = Field(
        default=None, description="The Qdrant failure message when search_sync_pending is set."
    )


class BulkChunkEnabledResponse(BaseModel):
    """
    The per-chunk outcomes of a bulk toggle plus the ids that did not resolve to a chunk.

    Attributes:
        results (list[ChunkEnabledResult]): One outcome per KNOWN chunk.
        not_found (list[str]): Requested ids with no matching chunk (skipped, not an error).
        search_sync_pending (bool): Postgres committed the toggles but the Qdrant payload sync failed —
            the search store is stale until a re-run/backfill reconciles it (the batch's truth).
        search_sync_error (str | None): The Qdrant failure message when ``search_sync_pending``.
    """

    results: list[ChunkEnabledResult] = Field(
        default_factory=list, description="One outcome per known chunk."
    )
    not_found: list[str] = Field(
        default_factory=list, description="Requested ids with no matching chunk."
    )
    search_sync_pending: bool = Field(
        default=False,
        description="Postgres committed but the Qdrant sync failed — stale until reconciled.",
    )
    search_sync_error: str | None = Field(
        default=None, description="The Qdrant failure message when search_sync_pending is set."
    )
