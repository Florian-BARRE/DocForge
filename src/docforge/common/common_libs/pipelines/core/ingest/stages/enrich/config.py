# ====== Code Summary ======
# IngestStageEnrichConfig - the per-collection PURE-SETTING knob of the enrich stage, co-located with
# the node and declared as its ``Config``. The enrich stage classifies each figure and routes it
# through the wired OCR / VLM / chart-to-data passes; this config holds only the stage's own plain
# settings, NOT the provider chains (classifier / OCR / VLM) or their gates - those describe how the
# assembler builds the injected chains and reach the stage as SERVICES, not as config. Every field
# carries a ``description`` so the discovery API renders a labelled form with zero hardcoded text.
# Frozen + strict (inherited from StageConfigBase): an out-of-contract value fails fast at assembly.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from common_libs.pipelines import StageConfigBase


class IngestStageEnrichConfig(StageConfigBase):
    """
    Enrich stage configuration - the stage's own pure-setting knobs.

    The OCR / VLM availability is DERIVED by the assembler from whether the collection wired an
    OCR / VLM chain, so it is an assembler-set constructor flag, not a user knob and not part of this
    config. Likewise the classifier / OCR / VLM provider chains and their escalation gates are
    assembled outside the node and injected as services. What remains here is the single chart pass
    toggle.

    Attributes:
        chart_to_data (bool): Extract a CHART-classified figure's series into a structured data table.
    """

    chart_to_data: bool = Field(
        default=True,
        description=(
            "When on, a figure classified as a CHART has its series extracted into a structured "
            "data table (in addition to the VLM description). Turn off to keep only the VLM "
            "description and skip the chart-to-data pass - e.g. when structured chart data is not "
            "needed for retrieval."
        ),
    )


__all__ = ["IngestStageEnrichConfig"]
