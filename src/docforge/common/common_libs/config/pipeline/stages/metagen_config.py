# ====== Code Summary ======
# MetaGenConfig + MetaGenTarget: configuration for the S5b "metagen" stage (LLM-generated metadata).
# Lives inside PipelineConfig.metagen — serialized in the collection's pipeline JSONB column.
# An empty config (no chain, no targets) is a complete no-op, so existing pipeline blobs are
# unaffected. The TWO-STEP model: a target only BINDS a provider + {field, prompt, scope}; the
# generated field's identity + searchable toggles live on its metadata_field row (origin="generated"),
# and the JSON output schema is auto-derived from each target field's type at runtime.
#
# LEAF CONSTRAINT: no module-level import of common_libs.providers / common_libs.pipeline —
# the concrete-provider coercion import stays LAZY (inside the model_validator body).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from common_libs.config.pipeline.chain_gate_config import ChainGateConfig


class MetaGenTarget(BaseModel):
    """
    One generation target: bind a generated metadata field to a prompt + scope.

    The ``field`` references an existing ``metadata_field`` row authored by the user with
    ``origin="generated"`` (step 1); this binding (step 2) only adds the extraction rule and
    the generation granularity. The JSON-schema type sent to the LLM is derived from that
    field's declared ``field_type`` (+ ``enum_values``), never configured here.

    Attributes:
        field (str): Name of the generated ``metadata_field`` this target populates.
        prompt (str): Extraction rule / instruction for the LLM (rendered as a textarea).
        scope (Literal["chunk", "document"]): Generation granularity — ``"chunk"`` = one value
            per chunk (stored in ``chunk.derived_meta``); ``"document"`` = one aggregated value
            (merged into ``doc_meta``).
    """

    field: str = Field(..., min_length=1, description="Generated metadata field this target populates.")
    prompt: str = Field(
        default="",
        json_schema_extra={"ui": "text"},
        description="Extraction rule / instruction sent to the LLM (multiline).",
    )
    scope: Literal["chunk", "document"] = Field(
        default="chunk",
        description="Generation granularity: 'chunk' (per chunk) or 'document' (one aggregated value).",
    )


class MetaGenConfig(BaseModel):
    """
    Configuration for the S5b metagen stage.

    Defaults (empty chain, empty targets) reproduce the pre-S5b behavior exactly — the stage
    short-circuits to a no-op, so an absent or empty ``metagen`` block changes nothing.

    Attributes:
        chain (list): Ordered LLM provider configs (discriminated union); index 0 is preferred.
        targets (list[MetaGenTarget]): Field bindings; empty ⇒ no-op.
        gate (ChainGateConfig): Chain escalation + exhaustion policy. Defaults to
            ``failure_policy="continue"`` so a degraded LLM call leaves the field empty rather
            than failing the document.
        max_concurrency (int): Maximum concurrent chunk-scope LLM calls.
    """

    chain: list[Any] = Field(
        default_factory=list,
        description="Ordered LLM provider configs; index 0 is preferred.",
    )
    targets: list[MetaGenTarget] = Field(
        default_factory=list,
        description="Field bindings {field, prompt, scope}; empty disables the stage.",
    )
    gate: ChainGateConfig = Field(
        default_factory=lambda: ChainGateConfig(failure_policy="continue"),
        description="Chain escalation + exhaustion policy (defaults to continue/degrade).",
    )
    max_concurrency: int = Field(
        default=8,
        ge=1,
        le=64,
        description="Maximum concurrent chunk-scope LLM calls.",
    )

    @model_validator(mode="after")
    def _validate_and_default_chain(self) -> MetaGenConfig:
        """
        Coerce each raw-dict chain item through the LLM discriminated union.

        When the chain round-trips from DB/JSON as dicts, validate each through the single
        ``openai_compat`` LLM config so an unknown id raises ValidationError immediately. Items
        already model instances are left untouched. Mirrors QueryTransformConfig's coercion.
        """
        # 1. Nothing to coerce when the chain is empty or already fully typed.
        if not self.chain or all(not isinstance(item, dict) for item in self.chain):
            return self

        # 2. Lazy import preserves the leaf constraint (single llm provider id: "openai_compat").
        from pydantic import TypeAdapter

        from common_libs.providers.llm.openai_compat.config import OpenAICompatLLMConfig

        adapter = TypeAdapter(OpenAICompatLLMConfig)
        coerced = [
            adapter.validate_python(item) if isinstance(item, dict) else item
            for item in self.chain
        ]
        object.__setattr__(self, "chain", coerced)
        return self


__all__ = ["MetaGenConfig", "MetaGenTarget"]
