# ====== Code Summary ======
# IngestStageChunkConfig — the per-collection knobs of the chunk stage, co-located with the node and
# declared as its ``Config``. It captures the structure-aware chunking policy: the heading-promotion
# rules that rebuild the section skeleton, the merge/breadcrumb flags, the intra-section split method
# CHOICE and its params, the atomic-block guarantees, and the flat-vs-hierarchical emission mode.
# Every field carries a ``description`` so the discovery API renders a labelled form with zero
# hardcoded text. Frozen + strict (inherited from StageConfigBase): an out-of-contract value fails
# fast at assembly.
#
# SCOPE: this is the self-describing MANIFEST the assembler reads to BUILD the splitter SERVICE; the
# stage itself receives that built splitter via REQUIRES. The SemanticSplitter's embed provider is a
# provider-chain concern (which embedder, where) and is therefore intentionally ABSENT from
# ``IngestStageChunkSplitSemanticConfig`` — only the pure split params live here.

# ====== Standard Library Imports ======
from typing import Annotated, Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field

# ====== Internal Project Imports ======
from common_libs.pipelines import StageConfigBase

# Sensible default heading rules for FR/EN administrative + technical documents, ordered by priority
# (first matching pattern sets the level). They recover structure the parser flattened (numbered
# sections, ARTICLE/ANNEXE/PARTIE, bold-only titles).
_DEFAULT_HEADING_RULES: list[dict[str, object]] = [
    {"level": 1, "pattern": r"^\s*(PARTIE|TITRE|LIVRE|PART)\s+[IVXLC0-9]"},
    {"level": 1, "pattern": r"^\s*(ANNEXE|ANNEX|APPENDIX)\s+[A-Z0-9]"},
    {"level": 2, "pattern": r"^\s*(CHAPITRE|CHAPTER)\s+[IVXLC0-9]"},
    {"level": 2, "pattern": r"^\s*(ARTICLE|ART\.)\s+\d+"},
    {"level": 2, "pattern": r"^\*\*[A-ZÉÀÈÊÎÔÙÛÜÆŒ][^*]{2,}\*\*\s*$"},
    {"level": 3, "pattern": r"^\s*(SECTION|Section)\s+[\d.]+"},
    {"level": 3, "pattern": r"^\s*\d+\.\s+[A-ZÉÀÈÊÎÔÙÛÜÆŒ]"},
    {"level": 4, "pattern": r"^\s*\d+\.\d+\.?\s+\S"},
    {"level": 5, "pattern": r"^\s*\d+\.\d+\.\d+\.?\s+\S"},
]


class HeadingRule(BaseModel):
    """
    A regex rule promoting a matching line of text to a heading at a given level.

    Applied on top of the parser's own heading detection to catch structural titles the parser
    misses (e.g. "ARTICLE 5", "PARTIE I", "ANNEXE A", bold-only titles). Rules are evaluated in
    order; the first match wins.

    Attributes:
        level (int): Heading level assigned on match (1 = top level).
        pattern (str): Python regex tested against the (stripped) block text.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    level: int = Field(
        default=1,
        ge=1,
        le=8,
        description="Heading level assigned when the pattern matches (1 = top level).",
    )
    pattern: str = Field(
        description="Python regex tested against each stripped block of text to promote it to a heading.",
    )


class AtomicConfig(BaseModel):
    """
    Atomic-block policy — keep semantic units whole so they are never split mid-content.

    Attributes:
        tables (bool): A table is always one chunk, never split, regardless of size.
        figures (bool): A figure is always its own chunk (OCR + description + chart data).
        formulas (bool): A formula is never separated from the block that introduces it.
        keep_caption_with_figure (bool): Fold an adjacent caption into its figure/table chunk.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tables: bool = Field(
        default=True,
        description="Keep every table whole as a single chunk, never split regardless of token size.",
    )
    figures: bool = Field(
        default=True,
        description="Emit every figure as its own chunk (carrying OCR text, description, and chart data).",
    )
    formulas: bool = Field(
        default=True,
        description="Never separate a formula from the block that introduces it.",
    )
    keep_caption_with_figure: bool = Field(
        default=True,
        description="Fold a caption adjacent to a figure/table into that chunk instead of the text flow.",
    )


class IngestStageChunkSplitTokenBudgetConfig(BaseModel):
    """
    Token-budget split method — cut a section once it exceeds a fixed token budget.

    Fast and always available (no external infrastructure).

    Attributes:
        id (Literal): Discriminator selecting this split method.
        max_tokens (int): Token budget per chunk before an oversize section is split.
        overlap_blocks (int): Blocks repeated at the start of each split sub-chunk for continuity.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Literal["token_budget"] = "token_budget"
    max_tokens: int = Field(
        default=512,
        ge=64,
        le=4096,
        description="Token budget per chunk; a section larger than this is split into sub-chunks.",
    )
    overlap_blocks: int = Field(
        default=0,
        ge=0,
        le=8,
        description="Number of blocks repeated at the start of each split sub-chunk to preserve context.",
    )


class IngestStageChunkSplitSentenceWindowConfig(BaseModel):
    """
    Sentence-window split method — slide a fixed window of sentences with a configurable stride.

    Fast and always available (no external infrastructure).

    Attributes:
        id (Literal): Discriminator selecting this split method.
        window_sentences (int): Number of sentences per window.
        stride_sentences (int): Number of sentences advanced between consecutive windows.
        max_tokens (int): Token budget used as the packing reference for small sections.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Literal["sentence_window"] = "sentence_window"
    window_sentences: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Number of sentences contained in each sliding window.",
    )
    stride_sentences: int = Field(
        default=4,
        ge=1,
        le=50,
        description="Number of sentences advanced between consecutive windows (overlap = window - stride).",
    )
    max_tokens: int = Field(
        default=512,
        ge=64,
        le=4096,
        description="Token budget used as the packing reference when grouping small sibling sections.",
    )


class IngestStageChunkSplitSemanticConfig(BaseModel):
    """
    Semantic split method — place boundaries where adjacent sentences are most dissimilar.

    Requires an embedding provider at build time; that provider is a provider-chain concern resolved
    by the assembler (which embedder, where) and is intentionally NOT a knob of this config.

    Attributes:
        id (Literal): Discriminator selecting this split method.
        max_tokens (int): Hard cap per piece.
        min_tokens (int): Minimum size before a semantic cut is honoured.
        breakpoint_percentile (int): Distance percentile above which a boundary is placed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Literal["semantic"] = "semantic"
    max_tokens: int = Field(
        default=512,
        ge=64,
        le=4096,
        description="Hard upper bound on the token size of any semantically split piece.",
    )
    min_tokens: int = Field(
        default=128,
        ge=0,
        le=2048,
        description="Minimum piece size below which a candidate semantic boundary is ignored.",
    )
    breakpoint_percentile: int = Field(
        default=90,
        ge=50,
        le=99,
        description="Sentence-distance percentile above which a section boundary is placed (higher = fewer cuts).",
    )


# Discriminated union of the three intra-section split methods, keyed on the ``id`` field. The
# assembler builds the matching splitter SERVICE from the selected variant; the stage receives it.
IngestStageChunkSplitMethodConfig = Annotated[
    IngestStageChunkSplitTokenBudgetConfig
    | IngestStageChunkSplitSentenceWindowConfig
    | IngestStageChunkSplitSemanticConfig,
    Field(discriminator="id"),
]


class IngestStageChunkConfig(StageConfigBase):
    """
    Chunk stage configuration — the structure-aware chunking policy.

    The heading hierarchy (parser headings + ``heading_rules``) always forms the chunking skeleton;
    ``split_method`` is the configurable way an oversize section is divided; ``atomic`` keeps special
    blocks whole; ``hierarchical`` additionally emits a parent chunk per section over its children;
    ``cross_references`` links chunks that cite a figure/table/article to the target chunk.

    Attributes:
        heading_rules (list[HeadingRule]): Regex rules promoting text to headings, applied on top of
            the parser's headings to recover structure.
        merge_short_sections (bool): Fold heading-only / tiny sections into neighbours.
        reinject_breadcrumb (bool): Record the section breadcrumb on each chunk for downstream context.
        split_method (IngestStageChunkSplitMethodConfig): Intra-section split method choice + params.
        hierarchical (bool): Emit a parent chunk per section over its child chunks.
        atomic (AtomicConfig): Atomic-block policy for tables / figures / formulas / captions.
        cross_references (bool): Detect "see Figure 3 / Article 5" and link to the target chunk.
    """

    heading_rules: list[HeadingRule] = Field(
        default_factory=lambda: [HeadingRule(**r) for r in _DEFAULT_HEADING_RULES],
        description=(
            "Ordered regex rules that promote matching text to headings on top of the parser's own "
            "headings, rebuilding the section skeleton (numbered sections, ARTICLE/ANNEXE/PARTIE...)."
        ),
    )
    merge_short_sections: bool = Field(
        default=True,
        description=(
            "Pack heading-only or tiny sibling sections into their neighbours so a chunk is never just "
            "a title with no content (flat mode only)."
        ),
    )
    reinject_breadcrumb: bool = Field(
        default=True,
        description=(
            "Record the section breadcrumb on each chunk so split sub-chunks stay aware of their "
            "section context (later consumed by the contextualize stage for embed_text)."
        ),
    )
    split_method: IngestStageChunkSplitMethodConfig = Field(
        default_factory=IngestStageChunkSplitTokenBudgetConfig,
        description=(
            "How an oversize section is divided: token budget, sliding sentence window, or semantic "
            "boundary detection. The assembler builds the matching splitter from this selection."
        ),
    )
    hierarchical: bool = Field(
        default=False,
        description=(
            "Emit a parent chunk spanning each divided section over its child chunks; children are "
            "searched while the parent is returned for context."
        ),
    )
    atomic: AtomicConfig = Field(
        default_factory=AtomicConfig,
        description="Atomic-block policy that keeps tables, figures, formulas, and captions whole.",
    )
    cross_references: bool = Field(
        default=True,
        description="Detect cross-references (e.g. 'see Figure 3', 'Article 5') and link them to their target chunk.",
    )


__all__ = [
    "HeadingRule",
    "AtomicConfig",
    "IngestStageChunkSplitTokenBudgetConfig",
    "IngestStageChunkSplitSentenceWindowConfig",
    "IngestStageChunkSplitSemanticConfig",
    "IngestStageChunkSplitMethodConfig",
    "IngestStageChunkConfig",
]
