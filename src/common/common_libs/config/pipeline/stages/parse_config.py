# ====== Code Summary ======
# S1 ParseConfig: ingestion-side parser chain configuration for the DocForge pipeline.
# Wraps the ordered parser chain (Docling, …) with a gated escalation policy.
#
# LEAF CONSTRAINT: no module-level import of libs.providers / libs.data /
# libs.pipeline / libs.config — all concrete-provider imports stay LAZY
# (inside model_validator bodies).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from common_libs.config.pipeline.chain_gate_config import ChainGateConfig
from common_libs.config.pipeline._helpers import _lift_provider_to_chain


class ParseConfig(BaseModel):
    """
    S1 parsing configuration — ordered parser chain with gated escalation.

    A legacy ``{provider: {id, params}}`` document is automatically lifted to a
    single-entry chain so historical DB rows keep loading.

    Attributes:
        chain (list[ParserConfig]): Ordered parser backends; index 0 is tried first.
            Defaults to a single Docling entry.
        gate (ChainGateConfig): Escalation policy for this chain.
    """

    chain: list[Any] = Field(default_factory=list)
    gate: ChainGateConfig = Field(default_factory=ChainGateConfig)

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        """Lift legacy ``{provider: {...}}`` to ``{chain: [{...}]}`` and flatten entries."""
        if not isinstance(v, dict):
            return v
        v = dict(v)
        v = _lift_provider_to_chain(v, chain_key="chain", provider_key="provider")
        return v

    @model_validator(mode="after")
    def _validate_and_default_parse_chain(self) -> ParseConfig:
        """
        Validate each item in the parser chain via the discriminated union, then default.

        When the chain is empty: default to [DoclingConfig()].
        When items are dicts (round-tripped from DB/JSON): coerce them through the
        TypeAdapter so unknown ids raise ValidationError immediately (not at registry time).
        """
        # Lazy imports to preserve the leaf constraint.
        from typing import Annotated

        from pydantic import Field as _F
        from pydantic import TypeAdapter

        from common_libs.providers.parser.docling import DoclingConfig

        if not self.chain:
            object.__setattr__(self, "chain", [DoclingConfig()])
            return self

        # Build the discriminated union from all known parser configs.
        union = Annotated[DoclingConfig, _F(discriminator="id")]
        adapter = TypeAdapter(union)

        # Coerce/validate each item — raises ValidationError on unknown id.
        coerced = [
            adapter.validate_python(item) if isinstance(item, dict) else item
            for item in self.chain
        ]
        object.__setattr__(self, "chain", coerced)
        return self
