# ====== Code Summary ======
# S4 ChunkConfig: structure-aware chunking configuration for the DocForge pipeline.
# Controls heading-rule regex promotion, merge policy, intra-section split method
# (TokenBudget / Semantic / SentenceWindow), atomic-block guarantees, hierarchical
# chunk emission, and cross-reference detection.
#
# LEAF CONSTRAINT: no module-level import of libs.providers / libs.data /
# libs.pipeline / libs.config — all concrete-provider imports stay LAZY
# (inside model_validator bodies).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Local Project Imports ======
from common_libs.config.pipeline._type_aliases import DEFAULT_HEADING_RULES
from common_libs.config.pipeline.stages.heading_rule import AtomicConfig, HeadingRule
from common_libs.config.pipeline.spec_utils import flatten_provider_spec as _flatten_provider_spec


class ChunkConfig(BaseModel):
    """
    S4 chunking + S5 contextualization configuration (spec §4.5, §4.6).

    The heading hierarchy (parser headings + regex rules) always forms the chunking skeleton —
    that is the structure recovered from our enriched blocks.  ``split_method`` is the
    configurable, method-specific way an oversize section is divided; ``atomic`` keeps special
    blocks whole; ``hierarchical`` additionally emits a parent chunk per section over its
    children; ``cross_references`` links chunks that cite a figure/table/article to its chunk.

    Attributes:
        heading_rules (list[HeadingRule]): Regex rules promoting text to headings, applied on
            top of the parser's headings to recover structure (numbered sections, ARTICLE…).
        merge_short_sections (bool): Fold heading-only / tiny sections into neighbours so a
            chunk is never just a title with no content.
        reinject_breadcrumb (bool): Prepend the section breadcrumb to every chunk's embed_text
            so split sub-chunks stay aware of their section context.
        split_method (SplitMethodConfig): Typed intra-section split config (discriminated by id).
        hierarchical (bool): Emit a parent chunk per section (full section) over its child
            chunks; children are searched, the parent is returned for context (Axe 1).
        atomic (AtomicConfig): Atomic-block policy for tables / figures / formulas / captions.
        cross_references (bool): Detect "see Figure 3 / Article 5" and link to the target chunk.
    """

    heading_rules: list[HeadingRule] = Field(
        default_factory=lambda: [HeadingRule(**r) for r in DEFAULT_HEADING_RULES]
    )
    merge_short_sections: bool = True
    reinject_breadcrumb: bool = True
    split_method: Any = Field(default=None)
    hierarchical: bool = False
    atomic: AtomicConfig = Field(default_factory=AtomicConfig)
    cross_references: bool = True

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        """Flatten old {id, params} DB format for the split_method field."""
        # 1. Not a dict — pass through
        if not isinstance(v, dict):
            return v
        v = dict(v)
        # 2. Flatten split_method if it uses old {id, params} shape
        if "split_method" in v and isinstance(v["split_method"], dict):
            v["split_method"] = _flatten_provider_spec(v["split_method"])
        return v

    @model_validator(mode="after")
    def _set_default_split_method(self) -> ChunkConfig:
        """
        Coerce split_method into a typed config instance.

        When None: default to TokenBudgetConfig.
        When a dict: validate via the discriminated union (triggers @register imports).
        """
        # Lazy imports to preserve the leaf constraint.
        from typing import Annotated

        from pydantic import Field as _F
        from pydantic import TypeAdapter

        from common_libs.pipeline.stages.s4_chunk.strategies.params import (
            SemanticConfig,
            SentenceWindowConfig,
            TokenBudgetConfig,
        )

        if self.split_method is None:
            object.__setattr__(self, "split_method", TokenBudgetConfig())
            return self

        if isinstance(self.split_method, (TokenBudgetConfig, SemanticConfig, SentenceWindowConfig)):
            # Already a typed instance — nothing to do.
            return self

        if isinstance(self.split_method, dict):
            # Dict → validate via the typed discriminated union.
            union = Annotated[
                TokenBudgetConfig | SemanticConfig | SentenceWindowConfig,
                _F(discriminator="id"),
            ]
            adapter = TypeAdapter(union)
            object.__setattr__(self, "split_method", adapter.validate_python(self.split_method))

        return self
