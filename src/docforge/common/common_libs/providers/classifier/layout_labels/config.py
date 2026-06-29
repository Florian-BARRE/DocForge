# ====== Code Summary ======
# Configuration class for the heuristic layout-labels figure classifier.
# Registered under the "classifier" category via @register("classifier").
# build() instantiates LayoutLabelsClassifier from the sibling module.

from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, model_validator

from common_libs.config.pipeline._registry import register
from common_libs.config.pipeline.spec_utils import flatten_provider_spec as _flatten_provider_spec

# ====== Local Project Imports ======
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from common_libs.providers.classifier.layout_labels.provider import LayoutLabelsClassifier


@register("classifier")
class LayoutLabelsConfig(BaseModel):
    """
    Configuration for the heuristic layout-labels figure classifier.

    Config id: "layout_labels" — zero cost, always available, uses pixel stats + parser label hints.
    """

    _label: ClassVar[str] = "layout_labels — heuristic pixel-stats + parser-label classifier (cost=0)"
    _category: ClassVar[str] = "classifier"

    id: Literal["layout_labels"] = "layout_labels"

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        return _flatten_provider_spec(v)

    def build(self) -> LayoutLabelsClassifier:
        """Instantiate LayoutLabelsClassifier from this config."""
        from common_libs.providers.classifier.layout_labels.provider import LayoutLabelsClassifier  # lazy runtime brick (L3)
        return LayoutLabelsClassifier()

    def merge_defaults(self, cfg: Any) -> LayoutLabelsConfig:
        """Return self unchanged — no tuneable defaults for the heuristic classifier."""
        return self

    @classmethod
    def availability(cls, cfg: Any) -> tuple[bool, str]:
        """Always available — zero-cost heuristic, no external deps."""
        return True, "Heuristic · cost=0 · always available"
