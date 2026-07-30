# ---------------------- Search stage 1 — QUERY ---------------------- #
# The query-intake / query-transform family: normalise the caller's raw ask (and, later, understand
# / rewrite / expand it) into the retrieval-ready QuerySpec. Importing this family imports every
# node folder inside it, so each node self-registers simply by existing here.
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry

NodeRegistry.register_family(
    "query",
    title="Query",
    description=(
        "Turns the caller's raw ask into a retrieval-ready QuerySpec: normalise (trim, case-fold, "
        "structure filters, set depth), and — later — understand, rewrite or expand it. Pick the "
        "intake method; transforms stack ahead of encoding."
    ),
    mode=FamilyMode.STAGE,
)
NodeRegistry.auto_import(__name__)
