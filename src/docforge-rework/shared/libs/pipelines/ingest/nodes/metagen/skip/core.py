# ====== Code Summary ======
# The metagen SKIP node — a model-free ForEach terminal. It is the graph-level embodiment of the old
# metagen ``on_error=skip_fields`` policy: when a structgen chain exhausts every provider on a request,
# the body routes OnFailure here instead of failing the item, and this node emits an EMPTY GeneratedValues
# carrying the request's request_id / chunk_id. The document survives; only that request's fields stay
# absent. It makes NO model call (its whole point is to spend nothing), so it uniformly closes the
# ForEach body on the same GeneratedValues artefact the structgen steps produce.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import GeneratedValues, GenerationRequest


class MetagenSkipConfig(NodeConfig):
    """No knobs — the fail-soft terminal emits an empty result and spends nothing."""


class MetagenSkipConsumes(NodeInput):
    """Input: the request whose chain exhausted every provider (echoed for its keys)."""

    request: GenerationRequest = Field(
        description="The failed request — its request_id / chunk_id are echoed onto the empty result."
    )


class MetagenSkipProduces(NodeOutput):
    """Output: an empty GeneratedValues (the uniform ForEach-body terminal artefact)."""

    values: GeneratedValues = Field(
        description="Empty generated values keyed to the request — the fields stay absent."
    )


@NodeRegistry.register("metagen")
class MetagenSkipNode(ActionNode):
    """The fail-soft ForEach terminal — emit empty values so the document survives a failed request."""

    KIND = "metagen_skip"
    SELECTABLE = False  # internal fail-soft ForEach terminal — the stage builder emits it
    NAME = "Metagen skip"
    SUMMARY = "Emit empty generated values for a request whose generation chain failed."
    HOW_IT_WORKS = (
        "A model-free terminal wired OnFailure from a metagen chain's last step: it emits an empty "
        "GeneratedValues carrying the request's request_id / chunk_id, so the failed request's fields "
        "stay absent and the document survives (the graph form of on_error=skip_fields)."
    )
    Config = MetagenSkipConfig
    Consumes = MetagenSkipConsumes
    Produces = MetagenSkipProduces

    async def run(self, data: MetagenSkipConsumes) -> MetagenSkipProduces:
        """
        Emit empty generated values keyed to the failed request.

        Args:
            data (MetagenSkipConsumes): The failed request.

        Returns:
            MetagenSkipProduces: Empty values carrying the request's request_id / chunk_id.
        """
        request = data.request
        self.logger.debug(f"Skipping request '{request.request_id}' — fields left absent")
        return MetagenSkipProduces(
            values=GeneratedValues(
                request_id=request.request_id, chunk_id=request.chunk_id, values={}
            )
        )


__all__ = [
    "MetagenSkipNode",
    "MetagenSkipConfig",
    "MetagenSkipConsumes",
    "MetagenSkipProduces",
]
