# ---------------------- Family auto-discovery ---------------------- #
# Importing this family imports every provider folder inside it, so each node self-registers
# simply by existing here — no manual list to maintain.
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry

NodeRegistry.register_family(
    "llm",
    title="LLM",
    description=(
        "Chat-completions providers, interchangeable behind one face. Same-kind repetition with different configs is legitimate (cheap-then-strong escalation)."
    ),
    mode=FamilyMode.CHAIN,
)
NodeRegistry.auto_import(__name__)
