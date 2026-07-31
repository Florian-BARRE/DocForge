# ---------------------- Search stage 6 — RERANK ---------------------- #
# The rerank family: re-score the candidate pool with a stronger signal (a cross-encoder or an LLM
# listwise judge). This is the home of the fallback-chain machinery — each method's OUTPUT is
# scored, so a ScoreBelow edge can escalate cheap→robust→LLM.
from shared_libs.pipelines.registry import FamilyMode, NodeRegistry

NodeRegistry.register_family(
    "rerank",
    title="Rerank",
    description=(
        "Re-scores the candidate pool with a stronger signal — a cross-encoder or an LLM listwise "
        "judge. Each method's output is scored, so a ScoreBelow edge escalates cheap→robust→LLM and "
        "converges with FromFirst (an escalation chain)."
    ),
    mode=FamilyMode.CHAIN,
)
NodeRegistry.auto_import(__name__)
