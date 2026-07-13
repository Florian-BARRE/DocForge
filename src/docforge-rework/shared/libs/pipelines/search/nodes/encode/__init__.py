# ---------------------- Search stage 3 — ENCODE ---------------------- #
# The query-encode family: turn the QuerySpec's text into the SAME vector shapes the collection's
# chunks were indexed with, using the collection's OWN embedder (locked, not user-swappable — the
# shared-vector-space invariant). Importing this family imports its node folder.
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry

NodeRegistry.register_family(
    "encode",
    title="Encode",
    description=(
        "Encodes the query into the collection's vector space using the collection's OWN embedder "
        "(rebuilt from its stored blob). Dense always; sparse/colbert per the collection's config. "
        "Locked to one method — the query MUST share the chunks' vector space."
    ),
    mode=FamilyMode.EXCLUSIVE,
)
NodeRegistry.auto_import(__name__)
