# ---------------------- Family auto-discovery ---------------------- #
# Importing this family imports every provider folder inside it, so each node self-registers simply
# by existing here — no manual list to maintain. The shared base/ folder registers nothing.
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry

NodeRegistry.register_family(
    "structgen",
    title="Structured generation",
    description=(
        "Fills a set of typed contract fields from text with one structured-output LLM call: the "
        "field types force the schema, the returned values are strictly coerced. Interchangeable "
        "providers meant for escalation chains — a call succeeds or fails (no quality score), so "
        "chains fall through on failure only."
    ),
    mode=FamilyMode.CHAIN,
)
NodeRegistry.auto_import(__name__)
