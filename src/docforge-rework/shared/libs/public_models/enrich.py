# ====== Code Summary ======
# The enrich-stage PER-ITEM artefacts. Enrichment runs inside a ForEach: each figure of the IR
# becomes a FigureItem flowing through its own sub-graph run — classified (kind stamped), routed
# by a WhenEquals switch, optionally OCR'd (context filled, ScoreBelow escalation between
# providers), then described. Every branch terminates on an EnrichmentEntry — the ForEach's
# collection contract — which the apply node folds back into the IR. The attempt trace (which
# provider ran, scores, errors) lives in the engine's per-item execution records, not here.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Local Project Imports ======
from .base import Artifact


class FigureItem(Artifact):
    """
    One figure travelling through the enrich sub-graph.

    A flow artefact enriched as it moves: the classifier stamps ``kind``, an OCR provider fills
    ``context`` (nodes return updated COPIES — instances are shared across concurrent items).

    Attributes:
        block_id (str): The IR figure block this item belongs to.
        image (bytes): The rendered crop (PNG).
        page_coverage (float): Fraction of the page area the figure covers, in [0, 1] — feeds
            the classifier's full-page-scan heuristic.
        kind (str): The figure class stamped by the classifier ('' until classified).
        context (str): Text accumulated for downstream providers (e.g. the OCR reading).
    """

    block_id: str
    image: bytes
    page_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    kind: str = ""
    context: str = ""


class EnrichmentEntry(Artifact):
    """
    The uniform terminal of every enrich branch — what one figure's run collected.

    Attributes:
        block_id (str): The IR figure block to apply this entry to.
        kind (str): The figure class decided by the classifier.
        ocr_text (str | None): The OCR reading, when an OCR provider ran.
        description (str | None): The VLM description, when a VLM ran.
        data_table (list[list[str]] | None): Rows parsed from a chart, when requested.
    """

    block_id: str
    kind: str = ""
    ocr_text: str | None = None
    description: str | None = None
    data_table: list[list[str]] | None = None


__all__ = [
    "FigureItem",
    "EnrichmentEntry",
]
