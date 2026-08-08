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
from shared_libs.pipelines.base import NodeUsage
from shared_libs.pipelines.nodes.openai_compat import EndpointReachability, OpenAICompatHelpers
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

    async def preflight(self) -> None:
        """Verify the configured endpoint is reachable, before any spend.

        The endpoint is dual-sourced per field: an all-empty override (the chain head) inherits the
        request's endpoint at run time, which preflight cannot see — so it only probes when this
        step pins its own ``base_url``.
        """
        config: StructGenConfig = self.config
        if not config.base_url:
            return
        # The probe uses the dedicated preflight budget (always set), never the run-request
        # timeout_seconds (which defaults to 0 = "inherit the request's" and is not a probe cap).
        await EndpointReachability.check(
            node_kind=self.KIND,
            base_url=config.base_url,
            api_key=config.api_key,
            timeout_seconds=config.preflight_timeout_seconds,
        )

    async def _generate(
        self, schema: dict[str, Any], request: GenerationRequest, endpoint: OpenAICompatConfig
    ) -> dict[str, Any]:
        """Run the structured-output chat call for one request."""
        # 1. Build the client on the effective endpoint and constrain it to the schema. ``include_raw``
        #    keeps the underlying AIMessage alongside the parsed value so its token usage survives —
        #    plain ``with_structured_output`` would swallow it. The step's optional ``seed`` pins
        #    reproducibility when a deployment sets it.
        config: StructGenConfig = self.config
        model = OpenAICompatHelpers.chat(
            endpoint,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            seed=config.seed,
            max_retries=config.max_retries,
        )
        structured = model.with_structured_output(schema, include_raw=True)

        # 2. Invoke on the system prompt + the text to extract from — result is {"raw", "parsed", …}.
        result = await structured.ainvoke(
            [SystemMessage(content=request.system_prompt), HumanMessage(content=request.text)]
        )

        # 3. Stash the paid-call token usage (from the raw message) for the base ``run`` to stamp on
        #    the output; the parsed value is returned unchanged for the base to coerce.
        raw_message = result.get("raw") if isinstance(result, dict) else None
        self._last_usage = NodeUsage.from_usage_metadata(
            getattr(raw_message, "usage_metadata", None), endpoint.model
        )
        return dict(result["parsed"])


__all__ = ["StructGenOpenAICompatibleNode"]
