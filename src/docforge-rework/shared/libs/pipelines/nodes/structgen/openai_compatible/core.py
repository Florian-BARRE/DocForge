# ====== Code Summary ======
# The OpenAI-compatible structgen node — the first concrete child of BaseStructGenNode. It runs one
# structured-output call against any OpenAI-compatible chat endpoint: the field-derived JSON schema
# constrains the model (LangChain's with_structured_output), the system prompt and text come from the
# request, and the raw field mapping is returned for the base to coerce. Works against vLLM, OpenAI,
# any compatible server. This is byte-for-byte the call metagen's node did inline — now a reusable,
# chainable capability.

# ====== Third-Party Library Imports ======
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.openai_compat import OpenAICompatHelpers
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import GenerationRequest, OpenAICompatConfig

# ====== Local Project Imports ======
from ..base import BaseStructGenNode, StructGenConfig


@NodeRegistry.register("structgen")
class StructGenOpenAICompatibleNode(BaseStructGenNode):
    """Generate structured values via any OpenAI-compatible chat endpoint."""

    KIND = "openai_compatible"
    NAME = "OpenAI-compatible structured generation"
    SUMMARY = "Fill a set of typed fields from text via any OpenAI-compatible endpoint."
    HOW_IT_WORKS = (
        "Builds a strict JSON schema from the request's field types and runs one structured-output "
        "chat call (system prompt + text) constrained to it, returning the raw field values for the "
        "base to coerce. The endpoint is the step's override when set, else the request's own."
    )
    Config = StructGenConfig

    async def _generate(
        self, schema: dict[str, Any], request: GenerationRequest, endpoint: OpenAICompatConfig
    ) -> dict[str, Any]:
        """Run the structured-output chat call for one request."""
        # 1. Build the client on the effective endpoint and constrain it to the schema.
        model = OpenAICompatHelpers.chat(
            endpoint, temperature=request.temperature, max_tokens=request.max_tokens
        )
        structured = model.with_structured_output(schema)

        # 2. Invoke on the system prompt + the text to extract from.
        result = await structured.ainvoke(
            [SystemMessage(content=request.system_prompt), HumanMessage(content=request.text)]
        )
        return dict(result)


__all__ = ["StructGenOpenAICompatibleNode"]
