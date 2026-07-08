# ====== Code Summary ======
# The fixed I/O contract shared by every structgen provider: ONE GenerationRequest in (a single
# structured-output call fully described), ONE GeneratedValues out (the coerced result). PRODUCES is
# a plain NodeOutput — a structured-generation call succeeds or fails, it carries no quality score,
# so the node is NOT scored and its chains escalate on failure only. GeneratedValues is the uniform
# single-slot terminal a metagen ForEach body collects (the structgen analogue of EnrichmentEntry).

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeInput, NodeOutput
from shared_libs.public_models import GeneratedValues, GenerationRequest


class StructGenConsumes(NodeInput):
    """Input of any structgen provider — one structured-generation call to run."""

    request: GenerationRequest = Field(
        description="The structured-generation call to run (fields, text, primary endpoint)."
    )


class StructGenProduces(NodeOutput):
    """Output of any structgen provider — the call's coerced values (a single-slot terminal)."""

    values: GeneratedValues = Field(
        description="The coerced values, keyed back to the request's chunk (or the document)."
    )


__all__ = ["StructGenConsumes", "StructGenProduces"]
