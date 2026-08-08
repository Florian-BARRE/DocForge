# ====== Code Summary ======
# BaseStructGenNode — the abstract base of every structgen provider: it takes one GenerationRequest,
# derives the structured-output JSON schema from the fields, runs ONE structured call, and strictly
# coerces each returned value to its contract type (an uncoercible value is dropped, never emitted).
# The primary endpoint is DUAL-SOURCED PER FIELD: each override field (base_url/api_key/model/timeout)
# wins when set, else the request's own value — so the chain head leaves the override empty (inheriting
# the resolved per-field endpoint) and a fallback step pins some or all fields to a robust endpoint.
# Children implement ONLY `_generate`, the
# provider-specific model call (the schema in, the raw dict out), mirroring how a VLM child implements
# `_describe`. Being abstract (via `_generate`), this base is not registered and skips the strict
# interface check.

# ====== Standard Library Imports ======
from abc import abstractmethod
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeUsage
from shared_libs.public_models import GeneratedValues, GenerationRequest, OpenAICompatConfig

# ====== Local Project Imports ======
from .config import StructGenConfig
from .helpers import StructGenHelpers
from .io import StructGenConsumes, StructGenProduces


class BaseStructGenNode(ActionNode):
    """Abstract structgen provider: one request in, its coerced values out; children do `_generate`."""

    Consumes = StructGenConsumes
    Produces = StructGenProduces

    # Last paid-call token usage, stashed by ``_generate`` and lifted onto the output by ``run``.
    _last_usage: NodeUsage | None = None

    @abstractmethod
    async def _generate(
        self, schema: dict[str, Any], request: GenerationRequest, endpoint: OpenAICompatConfig
    ) -> dict[str, Any]:
        """
        Run the provider's structured-output call for one request.

        Args:
            schema (dict): The strict JSON object schema the field types force the output through.
            request (GenerationRequest): The call to run (system prompt, text, generation knobs).
            endpoint (OpenAICompatConfig): The effective endpoint (override or the request's own).

        Returns:
            dict: The raw field-name → value mapping the model returned (pre-coercion).
        """
        ...

    def _effective_endpoint(self, request: GenerationRequest) -> OpenAICompatConfig:
        """
        Resolve the call's endpoint — a configured step override wins, else the request's own.

        Args:
            request (GenerationRequest): The request carrying the resolved primary endpoint.

        Returns:
            OpenAICompatConfig: The endpoint the call must target.
        """
        config: StructGenConfig = self.config
        # Per-field dual-source: each override field wins when set, else the request's own value —
        # an all-empty override (the chain head) returns exactly the request's per-field endpoint.
        return OpenAICompatConfig(
            base_url=config.base_url or request.endpoint.base_url,
            api_key=config.api_key or request.endpoint.api_key,
            model=config.model or request.endpoint.model,
            timeout_seconds=config.timeout_seconds or request.endpoint.timeout_seconds,
        )

    async def run(self, data: StructGenConsumes) -> StructGenProduces:
        """
        Run one structured-generation call and coerce its values to the contract types.

        Args:
            data (StructGenConsumes): The request to fulfil.

        Returns:
            StructGenProduces: The coerced values, keyed back to the request's chunk/document.
        """
        request = data.request
        # 1. Dual-source endpoint — a configured override wins, else the request's own endpoint.
        endpoint = self._effective_endpoint(request)

        # 2. The field types force the output shape.
        schema = StructGenHelpers.object_schema([(f.spec, f.instruction) for f in request.fields])

        # 3. One structured-output call (the provider hook).
        raw = await self._generate(schema, request, endpoint)

        # 4. STRICT coercion — a wrong-typed value is dropped, never emitted.
        values: dict[str, Any] = {}
        for field in request.fields:
            coerced = StructGenHelpers.coerce(
                raw.get(field.spec.field_name), field.spec.field_type, field.spec.enum_values
            )
            if coerced is not None:
                values[field.spec.field_name] = coerced

        self.logger.debug(
            f"structgen '{self.KIND}' filled {len(values)}/{len(request.fields)} field(s)"
        )
        output = StructGenProduces(
            values=GeneratedValues(
                request_id=request.request_id, chunk_id=request.chunk_id, values=values
            )
        )
        # The paid-call token usage the provider stashed rides on the output for the engine to lift.
        output._usage = self._last_usage
        return output


__all__ = ["BaseStructGenNode"]
