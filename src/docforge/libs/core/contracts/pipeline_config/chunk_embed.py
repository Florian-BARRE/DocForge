# ====== Code Summary ======
# S4 ChunkConfig (+ HeadingRule and AtomicConfig supporting models),
# S5 ContextualizeConfig, and S6 EmbedConfig.
#
# ChunkConfig drives the structure-aware chunking engine: heading-rule regex
# promotion, merge policy, intra-section split method (TokenBudget / Semantic /
# SentenceWindow), atomic-block guarantees, hierarchical chunk emission, and
# cross-reference detection.
#
# ContextualizeConfig controls how each chunk's embed_text header is assembled
# before the embedder processes it.
#
# EmbedConfig wraps the ordered embedding-backend chain (TEI / LocalOpenAI /
# OpenAI) with a gated escalation policy.
#
# LEAF CONSTRAINT: no module-level import of libs.capabilities / libs.data /
# libs.engine / libs.governance — all concrete-provider imports stay LAZY
# (inside model_validator bodies).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Local Project Imports ======
from libs.core.contracts.chain_gate_config import ChainGateConfig
from libs.core.contracts.pipeline_config._helpers import _lift_provider_to_chain
from libs.core.contracts.pipeline_config._type_aliases import DEFAULT_HEADING_RULES
from libs.core.contracts.spec_utils import flatten_provider_spec as _flatten_provider_spec


# ──────────────────────────────────────────────────────────────────────────────
# S4 — Chunk supporting models
# ──────────────────────────────────────────────────────────────────────────────

class HeadingRule(BaseModel):
    """
    A regex rule that promotes a matching line of text to a heading at a given level.

    Applied on top of the parser's own heading detection to catch structural titles the
    parser misses (e.g. "ARTICLE 5", "PARTIE I", "ANNEXE A", bold-only titles, numbered
    sections).  Rules are evaluated in order; the first match wins.

    Attributes:
        level (int): Heading level assigned on match (1 = top level).
        pattern (str): Python regex tested against the (stripped) block text.
    """

    level: int = Field(default=1, ge=1, le=8)
    pattern: str


class AtomicConfig(BaseModel):
    """
    Atomic-block policy (spec §4.5 — special blocks): keep semantic units whole.

    Attributes:
        tables (bool): A TABLE is always a single chunk, never split (regardless of size).
        figures (bool): A FIGURE is always its own chunk (OCR + description + chart data).
        formulas (bool): A FORMULA is never separated from the block that introduces it.
        keep_caption_with_figure (bool): An adjacent CAPTION is folded into its FIGURE/TABLE
            chunk instead of drifting into the surrounding text flow.
    """

    tables: bool = True
    figures: bool = True
    formulas: bool = True
    keep_caption_with_figure: bool = True


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
    def _set_default_split_method(self) -> "ChunkConfig":
        """
        Coerce split_method into a typed config instance.

        When None: default to TokenBudgetConfig.
        When a dict: validate via the discriminated union (triggers @register imports).
        """
        # Lazy imports to preserve the leaf constraint.
        from libs.engine.stages.chunking.params import (
            TokenBudgetConfig,
            SemanticConfig,
            SentenceWindowConfig,
        )
        from typing import Annotated, Union
        from pydantic import TypeAdapter, Field as _F

        if self.split_method is None:
            object.__setattr__(self, "split_method", TokenBudgetConfig())
            return self

        if isinstance(self.split_method, (TokenBudgetConfig, SemanticConfig, SentenceWindowConfig)):
            # Already a typed instance — nothing to do.
            return self

        if isinstance(self.split_method, dict):
            # Dict → validate via the typed discriminated union.
            union = Annotated[
                Union[TokenBudgetConfig, SemanticConfig, SentenceWindowConfig],
                _F(discriminator="id"),
            ]
            adapter = TypeAdapter(union)
            object.__setattr__(self, "split_method", adapter.validate_python(self.split_method))

        return self


# ──────────────────────────────────────────────────────────────────────────────
# S5 — Contextualize
# ──────────────────────────────────────────────────────────────────────────────

class ContextualizeConfig(BaseModel):
    """
    S5 contextualization configuration — controls how each chunk's ``embed_text`` header
    is assembled before the embedder sees it.

    The default template is::

        <doc_title> > <H1> > <H2> > <H3>

        <chunk body>

    Toggle ``include_doc_title`` or ``include_breadcrumb`` to flatten the header; adjust
    ``breadcrumb_separator`` / ``header_body_separator`` to match the embedder's preferred
    style (e.g. some BGE-M3 prompts perform better with newlines instead of " > ").

    Attributes:
        include_doc_title (bool): Prepend ``DocumentIR.title`` to the header when the
            title is not already the first breadcrumb segment.
        include_breadcrumb (bool): Include the heading breadcrumb (``H1 > H2 > H3``).
            When False, only the doc title (if enabled) is prepended — the chunk body
            stays uncontextualised, which is sometimes useful for benchmarks.
        breadcrumb_separator (str): Joins title + breadcrumb segments (default ``" > "``).
        header_body_separator (str): Joins the header line to the chunk body
            (default ``"\\n\\n"``).
    """

    include_doc_title: bool = True
    include_breadcrumb: bool = True
    breadcrumb_separator: str = Field(default=" > ", min_length=1, max_length=8)
    header_body_separator: str = Field(default="\n\n", min_length=1, max_length=8)


# ──────────────────────────────────────────────────────────────────────────────
# S6 — Embed
# ──────────────────────────────────────────────────────────────────────────────

class EmbedConfig(BaseModel):
    """
    S6 embedding + indexing configuration (spec §4.7).

    Three backends are available:

    ``TeiEmbedConfig`` (id="tei") — local TEI server (BGE-M3, dense 1024-dim + sparse BM25).
        Required params: ``base_url`` (e.g. ``http://tei:8080``).
        Optional: ``model`` (default ``BAAI/bge-m3``), ``batch_size``, ``embed_sparse``.

    ``LocalOpenAIEmbedConfig`` (id="openai_compat") — self-hosted OpenAI-compatible server.
        Required params: ``base_url``.  Optional: ``api_key``, ``model``, ``batch_size``.

    ``OpenAIEmbedConfig`` (id="openai") — external cloud API (OpenAI, Azure, Mistral, Cohere).
        Required params: ``base_url``, ``api_key`` (mandatory — raises if empty).

    Attributes:
        chain (list[EmbedProviderConfig]): Ordered embedding backends; index 0 is tried first.
        gate (ChainGateConfig): Escalation policy for the embedding chain.
    """

    chain: list[Any] = Field(
        default_factory=list,
        description="Ordered embedding backends; index 0 is tried first.",
    )
    gate: ChainGateConfig = Field(
        default_factory=ChainGateConfig,
        description="Escalation policy for the embedding chain.",
    )

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
    def _validate_and_default_embed_chain(self) -> "EmbedConfig":
        """
        Validate each item in the embed chain via the discriminated union, then default.

        When the chain is empty: default to [TeiEmbedConfig()].
        When items are dicts (round-tripped from DB/JSON): coerce them through the
        TypeAdapter so unknown ids raise ValidationError immediately (not at registry time).
        """
        # Lazy imports to preserve the leaf constraint.
        from libs.capabilities.embed.local.tei import TeiEmbedConfig
        from libs.capabilities.embed.local.openai_compat import LocalOpenAIEmbedConfig
        from libs.capabilities.embed.external.openai_compat import OpenAIEmbedConfig
        from typing import Annotated, Union
        from pydantic import TypeAdapter, Field as _F

        if not self.chain:
            object.__setattr__(self, "chain", [TeiEmbedConfig()])
            return self

        # Build the discriminated union from all known embed configs.
        union = Annotated[
            Union[TeiEmbedConfig, LocalOpenAIEmbedConfig, OpenAIEmbedConfig],
            _F(discriminator="id"),
        ]
        adapter = TypeAdapter(union)

        # Coerce/validate each item — raises ValidationError on unknown id.
        coerced = [
            adapter.validate_python(item) if isinstance(item, dict) else item
            for item in self.chain
        ]
        object.__setattr__(self, "chain", coerced)
        return self
