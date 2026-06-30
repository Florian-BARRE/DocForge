# ====== Code Summary ======
# MetagenPreviewService — the business logic behind POST /collections/{id}/metagen/preview. Given a
# collection's pipeline + metadata schema, a target field name, and a piece of content (a chunk's
# text or an ad-hoc sample), it resolves the metagen target's prompt/scope and the field's declared
# type, builds the SAME strict JSON schema S5b uses at ingestion (MetagenSchemaBuilder), runs ONE
# generate_json call through the collection's LLM chain (per-collection URL+secret, never .env), and
# returns the generated value plus a coarse token/cost estimate. No persistence, no caching: a
# preview must be cheap, side-effect-free, and reflect exactly what ingestion would produce.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from common_libs.config.pipeline import PipelineConfig
from common_libs.domain.metadata.meta_field_spec import MetaFieldSpec
from common_libs.pipelines.builder.chain_builder import ChainBuilder
from common_libs.pipelines.metagen.helpers import (
    METAGEN_MAX_OUTPUT_TOKENS,
    MetagenPromptHelpers,
    MetagenSchemaBuilder,
)

# Coarse input-token proxy: ~4 characters per token (matches the metagen budget heuristic).
_CHARS_PER_TOKEN = 4


class MetagenPreviewError(Exception):
    """Raised when a metagen preview cannot be produced (bad target / field / provider)."""


@dataclass(frozen=True, slots=True)
class MetagenPreviewResult:
    """
    The outcome of a single metagen preview call.

    Attributes:
        value (Any): The generated value for the requested field (None when the LLM returned null
            or the call degraded).
        raw (dict): The full parsed JSON object the LLM returned (one key per scope-group target).
        token_estimate (int): Coarse total token estimate (input proxy + output budget).
        cost_estimate (float): Coarse USD cost estimate for this single call.
        scope (str): The target's generation scope ("chunk" / "document").
        provider (str | None): The provider that produced the result (None on a degraded chain).
        degraded (bool): True when the chain exhausted and returned an empty/best-effort result.
    """

    value: Any = None
    raw: dict[str, Any] = field(default_factory=dict)
    token_estimate: int = 0
    cost_estimate: float = 0.0
    scope: str = "chunk"
    provider: str | None = None
    degraded: bool = False


class MetagenPreviewService(LoggerClass):
    """
    Service that runs a single, side-effect-free metagen generation for prompt validation.

    Stateless apart from the injected RUNTIME_CONFIG (used to merge deployment defaults into the
    collection's per-collection provider config). One public coroutine, ``preview``.
    """

    def __init__(self, cfg: Any) -> None:
        """
        Wire the preview service.

        Args:
            cfg (Any): RUNTIME_CONFIG — deployment defaults merged into the collection's LLM spec.
        """
        LoggerClass.__init__(self)
        self._cfg = cfg

    async def preview(
        self,
        *,
        pipeline: dict[str, Any] | None,
        metadata_fields: list[Any],
        field_name: str,
        content_text: str,
        heading_path: str = "",
    ) -> MetagenPreviewResult:
        """
        Generate one metagen value for ``field_name`` over ``content_text``.

        Args:
            pipeline (dict | None): The collection's stored pipeline config (carries ``metagen``).
            metadata_fields (list): The collection's metadata fields (ORM rows or dicts).
            field_name (str): The generated field to preview (must have a bound metagen target).
            content_text (str): The text to extract from (a chunk's raw_text or a sample).
            heading_path (str): Optional chunk heading breadcrumb (chunk scope only).

        Returns:
            MetagenPreviewResult: The generated value + raw object + token/cost estimate.

        Raises:
            MetagenPreviewError: When no target binds the field, the field is not a resolvable
                generated field, or no usable LLM provider is configured.
        """
        # 1. Resolve the metagen config + the target bound to the requested field.
        metagen = PipelineConfig.from_dict(pipeline).metagen
        target = next((t for t in metagen.targets if t.field == field_name), None)
        if target is None:
            raise MetagenPreviewError(
                f"No metagen target binds field {field_name!r} — add one in the metagen config."
            )

        # 2. Resolve the field's declared type/enum (must be an origin='generated' field).
        spec = self._resolve_spec(metadata_fields, field_name)
        if spec is None:
            raise MetagenPreviewError(
                f"Field {field_name!r} is not a metadata field with origin='generated'."
            )

        # 3. Build the LLM chain from the collection's per-collection provider config (URL+secret).
        chain = self._build_chain(metagen)

        # 4. Build the strict schema + rule block (identical to S5b) and the scope-specific prompt.
        field_types = {field_name: spec}
        schema = MetagenSchemaBuilder.build_json_schema([target], field_types)
        rules = MetagenPromptHelpers.field_rules([target], field_types)
        prompt = self._build_prompt(target.scope, rules, heading_path, content_text)

        # 5. Run ONE generate_json call (no cache, no persistence) and shape the result.
        outcome = await chain.call(
            lambda p: p.generate_json(
                prompt, schema, max_tokens=METAGEN_MAX_OUTPUT_TOKENS, temperature=0.0
            )
        )
        data = outcome.result if isinstance(outcome.result, dict) else {}
        cost = MetagenPromptHelpers.estimate_call_cost(prompt, METAGEN_MAX_OUTPUT_TOKENS)
        tokens = int(len(prompt) / _CHARS_PER_TOKEN) + METAGEN_MAX_OUTPUT_TOKENS
        self.logger.info(
            f"Metagen preview: field={field_name!r} scope={target.scope} "
            f"provider={outcome.final_provider} degraded={outcome.degraded} est_cost=${cost:.4f}"
        )
        return MetagenPreviewResult(
            value=data.get(field_name),
            raw=data,
            token_estimate=tokens,
            cost_estimate=cost,
            scope=target.scope,
            provider=outcome.final_provider,
            degraded=outcome.degraded,
        )

    def _build_chain(self, metagen: Any) -> Any:
        """
        Build the metagen LLM chain (category "llm"), translating a bad provider into a preview error.

        The v2 ChainBuilder is PURE — it does NO availability probe (that is a config-validation /
        monitoring concern), so the only failure here is a provider config that cannot be instantiated
        (e.g. an incomplete per-collection URL/secret), which is surfaced as a preview error.

        Args:
            metagen (MetaGenConfig): The collection's metagen config block.

        Returns:
            Chain: The wired LLM chain.

        Raises:
            MetagenPreviewError: When no provider is configured or one cannot be instantiated.
        """
        # 1. Build the LLM escalation chain from the collection's per-collection provider specs.
        try:
            chain = ChainBuilder(self._cfg).build("llm", list(metagen.chain), metagen.gate)
        except Exception as exc:
            # The collection's metagen provider config is incomplete (e.g. missing base_url/api_key).
            raise MetagenPreviewError(str(exc)) from exc
        # 2. An empty chain (no providers) means nothing is configured — surface a clear error.
        if not chain.providers:
            raise MetagenPreviewError(
                "No LLM provider configured for metagen — add one to the metagen chain."
            )
        return chain

    @staticmethod
    def _build_prompt(scope: str, rules: str, heading_path: str, content_text: str) -> str:
        """Build the scope-appropriate extraction prompt (chunk vs document)."""
        if scope == "document":
            return MetagenPromptHelpers.build_doc_prompt(rules, "", content_text)
        return MetagenPromptHelpers.build_chunk_prompt(rules, heading_path, content_text)

    @staticmethod
    def _resolve_spec(metadata_fields: list[Any], field_name: str) -> MetaFieldSpec | None:
        """
        Resolve a generated field's declared type/enum into a MetaFieldSpec (or None when ineligible).

        Mirrors the registry's resolution: only a field authored with ``origin="generated"`` is
        eligible — the preview must never target a system/user field.

        Args:
            metadata_fields (list): The collection's metadata fields (ORM rows or dicts).
            field_name (str): The field to resolve.

        Returns:
            MetaFieldSpec | None: The resolved spec, or None when the field is missing or not generated.
        """
        def _attr(obj: Any, name: str, default: Any = None) -> Any:
            return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)

        for fld in metadata_fields or []:
            if _attr(fld, "field_name") != field_name or _attr(fld, "origin") != "generated":
                continue
            return MetaFieldSpec(
                field_name=field_name,
                field_type=_attr(fld, "field_type", "string"),
                enum_values=_attr(fld, "enum_values"),
                required=bool(_attr(fld, "required", False)),
                origin="generated",
            )
        return None


# ------------------- Public API ------------------- #
__all__ = ["MetagenPreviewService", "MetagenPreviewError", "MetagenPreviewResult"]
