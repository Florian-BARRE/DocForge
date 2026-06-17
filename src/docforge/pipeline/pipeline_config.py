# ====== Code Summary ======
# PipelineConfig — the per-collection / per-playground pipeline contract (spec §3, §6.1).
# Every ML brick is a typed discriminated union config (Pydantic v2), so providers are
# interchangeable and configurable on the fly — including credentials (API key, base URL,
# model) supplied at request time from the playground UI, not just deployment env vars.
#
# Discriminated unions use `id: Literal[...]` as the discriminator field, giving full
# type-safety and IDE support over the old free-form ProviderSpec(id, params) approach.
# Backward compat: `model_validator(mode="before")` in each sub-config flattens old
# {id, params} DB data via `_flatten_provider_spec` so existing stored configs still load.
#
# The ProviderRegistry resolves this config into concrete stages; the StageEngine honors it
# per-run, so the playground (dry_run) tunes the exact same engine full ingestion uses.
# The shape is described to the UI by GET /playground/stages so the configurator is generated.

# ====== Standard Library Imports ======
from __future__ import annotations

import re
from typing import Annotated, Any, Optional, Union

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field, model_validator

# ====== Internal Project Imports ======
from providers.converter.local.gotenberg import GotenbergConfig  # noqa: F401
from providers.parser.local.docling import DoclingConfig
from providers.classifier.local.layout_labels import LayoutLabelsConfig
from providers.classifier.local.vit_onnx import VitOnnxConfig
from providers.ocr.local.paddle_ocr import PaddleOcrConfig
from providers.ocr.external.mistral_ocr import MistralOcrConfig
from providers.vlm.local.openai_compat import LocalVlmConfig
from providers.vlm.external.openai_compat import OpenAIVlmConfig
from providers.embed.local.tei import TeiEmbedConfig
from providers.embed.local.openai_compat import LocalOpenAIEmbedConfig
from providers.embed.external.openai_compat import OpenAIEmbedConfig
from pipeline.stages.chunking.params import (
    TokenBudgetConfig,
    SemanticConfig,
    SentenceWindowConfig,
    SPLIT_METHOD_PARAMS,  # noqa: F401
)

# Param-name segments that mark a value as a credential — masked when the config is echoed.
# Matched against whole `_`/`-`-separated segments (not substrings) so legitimate keys like
# "max_tokens" are never mistaken for a "token" credential.
_SECRET_SEGMENTS = frozenset({"key", "apikey", "token", "secret", "password", "credential", "auth"})


def _is_secret_key(key: str) -> bool:
    """Return True when a param name denotes a credential (segment-exact match)."""
    return any(part in _SECRET_SEGMENTS for part in re.split(r"[_\-\s]+", key.lower()))


def _flatten_provider_spec(v: Any) -> Any:
    """
    Backward compat: flatten old ProviderSpec {id, params} format into a flat dict.

    Old DB rows store configs as ``{"id": "tei", "params": {"base_url": "http://tei:8080"}}``.
    The new typed union members expect the flat form ``{"id": "tei", "base_url": "http://tei:8080"}``.
    This helper is called from model_validator(mode="before") in each sub-config.

    Args:
        v (Any): Raw value coming in (dict or already-parsed model).

    Returns:
        Any: Flattened dict if it was an old-style {id, params} dict; unchanged otherwise.
    """
    if isinstance(v, dict) and "params" in v and isinstance(v.get("params"), dict):
        return {"id": v.get("id"), **v["params"]}
    return v


# ====== Discriminated Union Type Aliases ======

# Only docling for now — Literal union extends naturally when marker/tika are typed.
ParserConfig = Annotated[DoclingConfig, Field(discriminator="id")]

ClassifierConfig = Annotated[
    Union[LayoutLabelsConfig, VitOnnxConfig],
    Field(discriminator="id"),
]

OcrProviderConfig = Annotated[
    Union[PaddleOcrConfig, MistralOcrConfig],
    Field(discriminator="id"),
]

VlmProviderConfig = Annotated[
    Union[LocalVlmConfig, OpenAIVlmConfig],
    Field(discriminator="id"),
]

EmbedProviderConfig = Annotated[
    Union[TeiEmbedConfig, LocalOpenAIEmbedConfig, OpenAIEmbedConfig],
    Field(discriminator="id"),
]

SplitMethodConfig = Annotated[
    Union[TokenBudgetConfig, SemanticConfig, SentenceWindowConfig],
    Field(discriminator="id"),
]


# ====== Backward-compat ProviderSpec (kept for other modules that import it) ======

class ProviderSpec(BaseModel):
    """
    A single provider selection with its own configuration parameters.

    Kept for backward compatibility — internal code should migrate to typed union configs.

    Attributes:
        id (str): Provider identifier (e.g. "mistral_ocr", "paddle_ocr", "openai_compat").
        params (dict): Free-form provider params — credentials (api_key), endpoints
            (base_url), model ids, device flags.  Missing params fall back to deployment
            defaults in the registry.  This is what lets the UI supply a key on the fly.
    """

    id: str
    params: dict[str, Any] = Field(default_factory=dict)


# ====== Sub-configs ======

class ParseConfig(BaseModel):
    """
    S1 parsing configuration.

    Attributes:
        provider (ParserConfig): Parser backend (discriminated by id: "docling") + typed params.
    """

    provider: ParserConfig = Field(default_factory=DoclingConfig)

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        """Flatten old {provider: {id, params}} DB format."""
        # 1. Not a dict — pass through (already a model instance)
        if not isinstance(v, dict):
            return v
        # 2. Flatten nested provider spec if it uses old {id, params} shape
        if "provider" in v and isinstance(v["provider"], dict):
            v = dict(v)
            v["provider"] = _flatten_provider_spec(v["provider"])
        return v


class EnrichConfig(BaseModel):
    """
    S2 enrichment configuration — figure classifier + OCR chain + VLM (spec §4.3).

    The ``vlm`` provider selects the Vision-Language Model backend used for figure
    grounding, chart description, and diagram captioning.  Two backends are available:

    ``LocalVlmConfig`` (id="openai_compat") — local OpenAI-compatible server (vLLM, Ollama).
        No api_key required (can be omitted or set to any placeholder).
        Required params: ``base_url``, ``model``.  Optional: ``api_key``, ``max_tokens``.

    ``OpenAIVlmConfig`` (id="openai") — external cloud API (OpenAI, Mistral, OpenRouter, …).
        ``api_key`` is REQUIRED — raises at provider init if empty or missing.
        Required params: ``base_url``, ``api_key``, ``model``.
        Optional: ``max_tokens``, ``cost_per_call`` (float, USD; used for budget tracking).

    Attributes:
        chart_to_data (bool): Extract chart series into a structured data_table.
        max_budget_usd (float): Per-job spend cap in USD. 0.0 = no limit.
        classifier (ClassifierConfig): Figure kind classifier (layout_labels / vit_onnx).
        ocr_chain (list[OcrProviderConfig]): Ordered OCR escalation chain, each with its own
            typed params (api_key, base_url, model, use_gpu). Empty = no OCR.
        vlm (VlmProviderConfig | None): VLM provider (openai_compat / openai) with typed params,
            or None to disable VLM enrichment entirely.
    """

    chart_to_data: bool = False
    max_budget_usd: float = 0.0
    classifier: ClassifierConfig = Field(default_factory=LayoutLabelsConfig)
    ocr_chain: list[OcrProviderConfig] = Field(default_factory=list)
    vlm: Optional[VlmProviderConfig] = None

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        """Flatten old {id, params} DB format for classifier, ocr_chain entries, and vlm."""
        # 1. Not a dict — pass through
        if not isinstance(v, dict):
            return v
        v = dict(v)
        # 2. Flatten classifier spec
        if "classifier" in v and isinstance(v["classifier"], dict):
            v["classifier"] = _flatten_provider_spec(v["classifier"])
        # 3. Flatten each entry in ocr_chain
        if "ocr_chain" in v and isinstance(v["ocr_chain"], list):
            v["ocr_chain"] = [
                _flatten_provider_spec(item) if isinstance(item, dict) else item
                for item in v["ocr_chain"]
            ]
        # 4. Flatten vlm spec
        if "vlm" in v and isinstance(v["vlm"], dict):
            v["vlm"] = _flatten_provider_spec(v["vlm"])
        return v


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


# Sensible default heading rules for FR/EN administrative + technical documents.
# Ordered by priority — the first matching pattern sets the heading level. Used to recover
# structure the parser flattened (numbered sections, ARTICLE/ANNEXE/PARTIE, bold titles).
DEFAULT_HEADING_RULES: list[dict[str, Any]] = [
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


# Intra-section split methods understood by S4 (the "decision tree" discriminator).
# Each method reads its own keys from its typed config (see params.py + SplitMethodConfig).
SPLIT_METHODS: frozenset[str] = frozenset({"token_budget", "semantic", "sentence_window"})


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
    split_method: SplitMethodConfig = Field(default_factory=TokenBudgetConfig)
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


class EmbedConfig(BaseModel):
    """
    S6 embedding + indexing configuration (spec §4.7).

    The ``provider.id`` selects the embedding backend.  Three backends are available:

    ``TeiEmbedConfig`` (id="tei") — local TEI server (BGE-M3, dense 1024-dim + sparse BM25).
        Required params: ``base_url`` (e.g. ``http://tei:8080``).
        Optional: ``model`` (default ``BAAI/bge-m3``), ``batch_size``, ``embed_sparse``.

    ``LocalOpenAIEmbedConfig`` (id="openai_compat") — self-hosted OpenAI-compatible server.
        Required params: ``base_url`` (e.g. ``http://vllm:8000/v1``).
        Optional: ``api_key``, ``model``, ``batch_size``, ``dimension``.
        Dense-only: no sparse vectors.

    ``OpenAIEmbedConfig`` (id="openai") — external cloud API (OpenAI, Azure, Mistral, Cohere).
        Required params: ``base_url``, ``api_key`` (mandatory — raises if empty).
        Optional: ``model`` (default ``text-embedding-3-large``), ``batch_size``, ``dimension``.
        Dense-only: no sparse vectors.

    Attributes:
        provider (EmbedProviderConfig): Embedding backend selection + its typed params.
    """

    provider: EmbedProviderConfig = Field(default_factory=TeiEmbedConfig)

    @model_validator(mode="before")
    @classmethod
    def _compat(cls, v: Any) -> Any:
        """Flatten old {provider: {id, params}} DB format."""
        # 1. Not a dict — pass through
        if not isinstance(v, dict):
            return v
        v = dict(v)
        # 2. Flatten nested provider spec if it uses old {id, params} shape
        if "provider" in v and isinstance(v["provider"], dict):
            v["provider"] = _flatten_provider_spec(v["provider"])
        return v


class PipelineConfig(BaseModel):
    """
    The full per-collection / per-playground pipeline contract.

    Attributes:
        parse (ParseConfig): S1 parsing.
        enrich (EnrichConfig): S2 enrichment.
        chunk (ChunkConfig): S4 chunking + S5 contextualization.
        embed (EmbedConfig): S6 embedding + indexing.
    """

    parse: ParseConfig = Field(default_factory=ParseConfig)
    enrich: EnrichConfig = Field(default_factory=EnrichConfig)
    chunk: ChunkConfig = Field(default_factory=ChunkConfig)
    embed: EmbedConfig = Field(default_factory=EmbedConfig)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "PipelineConfig":
        """
        Build a PipelineConfig from a (possibly empty/partial) JSON dict.

        An empty/None dict falls back to defaults; a partial dict fills the rest from defaults.

        Args:
            raw (dict | None): Serialized config (collection.pipeline jsonb or request body).

        Returns:
            PipelineConfig: Parsed config with defaults filled in.
        """
        if not raw:
            return cls()
        return cls.model_validate(raw)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain JSON-compatible dict (for collection.pipeline storage)."""
        return self.model_dump(mode="json")

    def redacted_dict(self) -> dict[str, Any]:
        """
        Serialize with all credential params masked — safe to echo to clients and logs.

        Returns:
            dict: The config with secret provider params replaced by "•••".
        """
        return _redact(self.model_dump(mode="json"))


def _redact(value: Any) -> Any:
    """Recursively mask secret-looking keys in a JSON-compatible structure."""
    # 1. Dict → mask matching keys, recurse into the rest
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and _is_secret_key(k) and v:
                out[k] = "•••"
            else:
                out[k] = _redact(v)
        return out
    # 2. List → recurse element-wise
    if isinstance(value, list):
        return [_redact(v) for v in value]
    # 3. Scalar → unchanged
    return value


def build_default_pipeline(cfg: Any) -> "PipelineConfig":
    """
    Build the default PipelineConfig from RUNTIME_CONFIG deployment env vars.

    This is the single authoritative translation from env-var booleans to a
    typed discriminated-union config.  Both entrypoint.py and worker.py call
    this instead of direct provider instantiation.

    Args:
        cfg: RUNTIME_CONFIG instance with all deployment env vars.

    Returns:
        PipelineConfig: Fully typed config representing the deployment's default stack.
    """
    # 1. Parser
    parse_cfg = ParseConfig(
        provider=DoclingConfig(use_gpu=getattr(cfg, "DOCLING_USE_GPU", False))
    )

    # 2. Figure classifier
    classifier_type = getattr(cfg, "CLASSIFIER_TYPE", "layout_labels")
    if classifier_type == "vit_onnx":
        classifier = VitOnnxConfig(
            model_path=getattr(cfg, "CLASSIFIER_ONNX_MODEL_PATH", ""),
            use_gpu=getattr(cfg, "CLASSIFIER_USE_GPU", False),
        )
    else:
        classifier = LayoutLabelsConfig()

    # 3. OCR chain
    ocr_chain: list = []
    if getattr(cfg, "OCR_PADDLE_ENABLED", False):
        ocr_chain.append(PaddleOcrConfig(use_gpu=getattr(cfg, "OCR_PADDLE_USE_GPU", False)))
    if getattr(cfg, "MISTRAL_OCR_ENABLED", False):
        ocr_chain.append(MistralOcrConfig(
            api_key=getattr(cfg, "MISTRAL_OCR_API_KEY", ""),
            base_url=getattr(cfg, "MISTRAL_OCR_API_URL", "https://api.mistral.ai/v1"),
            model=getattr(cfg, "MISTRAL_OCR_MODEL", "mistral-ocr-latest"),
            timeout_s=getattr(cfg, "MISTRAL_OCR_TIMEOUT_S", 60),
        ))

    # 4. VLM
    vlm_cfg = None
    if getattr(cfg, "VLM_ENABLED", False):
        vlm_cfg = LocalVlmConfig(
            base_url=getattr(cfg, "VLM_API_BASE_URL", ""),
            api_key=getattr(cfg, "VLM_API_KEY", ""),
            model=getattr(cfg, "VLM_MODEL", ""),
            timeout_s=getattr(cfg, "VLM_TIMEOUT_S", 30),
            max_tokens=getattr(cfg, "VLM_MAX_TOKENS", 1024),
            cost_per_call=getattr(cfg, "VLM_COST_PER_CALL", 0.0),
        )

    enrich_cfg = EnrichConfig(
        classifier=classifier,
        ocr_chain=ocr_chain,
        vlm=vlm_cfg,
        max_budget_usd=getattr(cfg, "ENRICH_MAX_BUDGET_USD", 0.0),
    )

    # 5. Chunking
    chunk_cfg = ChunkConfig(
        split_method=TokenBudgetConfig(
            max_tokens=getattr(cfg, "CHUNK_MAX_TOKENS", 512),
            overlap_blocks=getattr(cfg, "CHUNK_OVERLAP_BLOCKS", 0),
        )
    )

    # 6. Embedding
    embed_cfg = EmbedConfig(
        provider=TeiEmbedConfig(
            base_url=getattr(cfg, "TEI_BASE_URL", "http://tei:8080"),
            batch_size=getattr(cfg, "TEI_BATCH_SIZE", 32),
        )
    )

    return PipelineConfig(parse=parse_cfg, enrich=enrich_cfg, chunk=chunk_cfg, embed=embed_cfg)
