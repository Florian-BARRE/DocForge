# ====== Code Summary ======
# The chart step's own failure type - raised when mining the VLM structured output into a data table
# fails. Pure post-processing, so a failure here is a contract/shape error rather than a transient
# one.

# ====== Internal Project Imports ======
from ..base import IngestStageEnrichStepError


class IngestStageEnrichStepChartError(IngestStageEnrichStepError):
    """Raised when the chart-to-data extraction pass fails."""

    code = "enrich_chart_failed"
    description = "The enrich chart-to-data pass (table extraction from VLM output) failed."


__all__ = ["IngestStageEnrichStepChartError"]
