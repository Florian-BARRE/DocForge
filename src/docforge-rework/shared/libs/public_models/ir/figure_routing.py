# ====== Code Summary ======
# THE single source of the figure taxonomy's behaviour: for every FigureKind, how the enrichment
# treats it (which model family, or a zero-spend decorative skip) and the one-line class description
# the classifier prompt lists for it. FigureKind (enums.py) stays the identity; this table hangs the
# routing off each member so the classifier prompt, the enrich branch table and the decorative skip
# all DERIVE from one place. The module-level completeness guard makes drift impossible: adding a
# FigureKind without its routing fails at IMPORT — long before any collection build or spend.

# ====== Standard Library Imports ======
from dataclasses import dataclass

# ====== Local Project Imports ======
from .enums import FigureKind


@dataclass(frozen=True)
class FigureRouting:
    """
    How one figure class is enriched — the per-FigureKind routing and prompt metadata.

    Attributes:
        family (str | None): The model family the class is enriched by (``ocr`` / ``vlm``), or
            None when the class is a decorative, zero-spend skip (no model call).
        title (str): Human label of the class's enrichment branch (surfaced in the studio).
        description (str): What the class's enrichment branch does, in one sentence.
        prompt (str): The one-line class description the classifier prompt lists for this class.
    """

    family: str | None
    title: str
    description: str
    prompt: str

    @property
    def decorative(self) -> bool:
        """Whether the class is the zero-spend skip (no model family, routed to the terminal)."""
        return self.family is None


# The taxonomy table — ONE entry per FigureKind (completeness enforced below). The order matches the
# enrich branch rail the studio renders: scanned text, then the visual classes, then the skip.
FIGURE_ROUTING: dict[FigureKind, FigureRouting] = {
    FigureKind.SCANNED_TEXT: FigureRouting(
        family="ocr",
        title="Scanned-text OCR",
        description="Read the text of a scanned region — a cheap local reader first, a robust "
        "one rescuing low scores and failures.",
        prompt="an image that is mostly printed or handwritten TEXT (a scanned page/region)",
    ),
    FigureKind.PHOTO: FigureRouting(
        family="vlm",
        title="Photo caption",
        description="Caption a photograph or natural illustration for retrieval.",
        prompt="a photograph or natural illustration",
    ),
    FigureKind.CHART: FigureRouting(
        family="vlm",
        title="Chart reading",
        description="Read a chart and transcribe its underlying data as a table.",
        prompt="a data visualisation (bar/line/pie chart, plot)",
    ),
    FigureKind.DIAGRAM: FigureRouting(
        family="vlm",
        title="Diagram rewrite",
        description="Rewrite a schematic or diagram as searchable text.",
        prompt="a schematic (architecture, flowchart, circuit, map)",
    ),
    FigureKind.DECORATIVE: FigureRouting(
        family=None,
        title="Decorative skip",
        description="A logo, separator, banner or ornament — skipped with no model call.",
        prompt="a logo, separator, banner or ornament with no informative content",
    ),
}


# THE coupling guard: every FigureKind MUST carry routing. A new enum member with no entry here
# fails at import (so every test run and every collection build breaks loudly) with an actionable
# message — never a silent unrouted class that stalls the classifier and fails a whole document.
_missing_routing = set(FigureKind) - set(FIGURE_ROUTING)
if _missing_routing:
    raise RuntimeError(
        "FigureKind members without routing metadata: "
        f"{sorted(kind.value for kind in _missing_routing)}. Add each to FIGURE_ROUTING (a model "
        "family + a classifier prompt line, or family=None for a decorative skip) so the "
        "classifier and the enrich stage route it."
    )


def figure_prompt_lines() -> str:
    """
    Build the per-class lines of the classifier prompt from the routing table.

    Returns:
        str: One ``- <kind>: <description>`` line per FigureKind, newline-joined.
    """
    return "\n".join(
        f"- {kind.value}: {routing.prompt}" for kind, routing in FIGURE_ROUTING.items()
    )


__all__ = ["FigureRouting", "FIGURE_ROUTING", "figure_prompt_lines"]
