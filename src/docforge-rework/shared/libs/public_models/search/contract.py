# ====== Code Summary ======
# SearchContract — the search run-input that carries the collection's identity + the collection's
# OWN embedder blob (kind + validated config) + its filterable field names. The query-encode node
# rebuilds the exact embedder from this blob (registry class + extra="forbid" config, so a drifted
# blob fails loudly) to encode the query into the SAME vector space the chunks were indexed with —
# the shared-vector-space invariant. It is built from the collection's INGEST blob
# (collection.pipeline) — the embedder the chunks were actually indexed with — NEVER from
# collection.search (a retrieval-tuning blob with no embedder), or queries encode into a different
# space than the index and retrieval silently degrades.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from ..base import Artifact


class SearchContract(Artifact):
    """
    The search run-input contract — the collection's identity + its embedder + its filter surface.

    Attributes:
        collection_id (str): The collection being searched (provenance; the port scopes to it).
        embed_kind (str): The registered embedder kind the collection indexed with (e.g.
            ``"bge_server"``) — the encode node rebuilds that exact class.
        embed_config (dict): The embedder's stored, validated config (endpoint, model, axes).
            Re-validated against the class's Config (extra="forbid") when the encode node runs.
        filterable_fields (list[str]): The contract field names a filter may target — the
            query-intake node drops (and notes) any filter outside this set.
        semantic_fields (list[str]): The metadata field names indexed with a dense vector — a
            semantic search target may name one of these (or ``"content"``); others are rejected.
        lexical_fields (list[str]): The metadata field names indexed with a sparse BM25 vector — a
            lexical search target may name one of these (or ``"content"``); others are rejected.
    """

    collection_id: str = Field(description="The collection being searched (provenance / port scope).")
    embed_kind: str = Field(description="The registered embedder kind the collection indexed with.")
    embed_config: dict = Field(
        default_factory=dict,
        description="The embedder's stored, validated config (endpoint, model, axes).",
    )
    filterable_fields: list[str] = Field(
        default_factory=list,
        description="Contract field names a filter may target (others are dropped and noted).",
    )
    semantic_fields: list[str] = Field(
        default_factory=list,
        description="Metadata field names with a dense vector (a semantic target may name one).",
    )
    lexical_fields: list[str] = Field(
        default_factory=list,
        description="Metadata field names with a sparse BM25 vector (a lexical target may name one).",
    )


__all__ = ["SearchContract"]
