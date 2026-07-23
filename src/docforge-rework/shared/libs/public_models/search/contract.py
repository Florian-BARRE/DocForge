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
    The search run-input contract — the collection's identity + its embedder.

    Only the embedder half is consumed downstream: the encode node rebuilds the exact embedder
    from ``embed_kind``/``embed_config`` to encode the query into the collection's vector space.
    Target/filter validation is done router-side against the live DB schema (not from this
    contract), so no field-list surface is carried here.

    Attributes:
        collection_id (str): The collection being searched (provenance only).
        embed_kind (str): The registered embedder kind the collection indexed with (e.g.
            ``"bge_server"``) — the encode node rebuilds that exact class.
        embed_config (dict): The embedder's stored, validated config (endpoint, model, axes).
            Re-validated against the class's Config (extra="forbid") when the encode node runs.
    """

    collection_id: str = Field(description="The collection being searched (provenance only).")
    embed_kind: str = Field(description="The registered embedder kind the collection indexed with.")
    embed_config: dict = Field(
        default_factory=dict,
        description="The embedder's stored, validated config (endpoint, model, axes).",
    )


__all__ = ["SearchContract"]
