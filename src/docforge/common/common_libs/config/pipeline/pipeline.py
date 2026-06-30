# ====== Code Summary ======
# Top-level PipelineConfig model and build_default_pipeline() factory.
#
# PipelineConfig is the per-collection / per-playground pipeline contract
# (spec section 3, section 6.1): it composes all stage configs (ParseConfig -> EnrichConfig
# -> ChunkConfig -> ContextualizeConfig -> EmbedConfig) into a single serialisable
# Pydantic document.
#
# build_default_pipeline() translates RUNTIME_CONFIG deployment env-vars into a
# fully-typed config; both entrypoint.py and worker.py call it instead of
# constructing providers directly.
#
# LEAF CONSTRAINT: no module-level import of libs.providers / libs.data /
# libs.pipeline / libs.config -- all concrete-provider imports stay LAZY
# (inside the function body of build_default_pipeline).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any, ClassVar

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Local Project Imports ======
from common_libs.config.pipeline.chain_gate_config import ChainGateConfig
from common_libs.config.pipeline._helpers import _redact
from common_libs.config.pipeline.stages.chunk_config import ChunkConfig
from common_libs.config.pipeline.stages.contextualize_config import ContextualizeConfig
from common_libs.config.pipeline.stages.embed_config import EmbedConfig
from common_libs.config.pipeline.stages.enrich_config import EnrichConfig
from common_libs.config.pipeline.stages.metagen_config import MetaGenConfig
from common_libs.config.pipeline.stages.parse_config import ParseConfig
from common_libs.config.pipeline.stages.search_config import SearchConfig


class PipelineConfig(BaseModel):
    """
    The full per-collection / per-playground pipeline contract.

    Attributes:
        parse (ParseConfig): S1 parsing.
        enrich (EnrichConfig): S2 enrichment.
        chunk (ChunkConfig): S4 chunking + S5 contextualization.
        contextualize (ContextualizeConfig): S5 contextualization options.
        metagen (MetaGenConfig): S5b LLM-generated metadata (runs after S5, before S6).
        embed (EmbedConfig): S6 embedding + indexing.
    """

    parse: ParseConfig = Field(default_factory=ParseConfig)
    enrich: EnrichConfig = Field(default_factory=EnrichConfig)
    chunk: ChunkConfig = Field(default_factory=ChunkConfig)
    contextualize: ContextualizeConfig = Field(default_factory=ContextualizeConfig)
    metagen: MetaGenConfig = Field(default_factory=MetaGenConfig)
    embed: EmbedConfig = Field(default_factory=EmbedConfig)
    search: SearchConfig = Field(default_factory=SearchConfig)

    # The per-stage config blocks, in pipeline order — the keys of the keyed-map (`stages`) view
    # and the un-nest target for the new keyed shape in ``from_dict``. ``search`` stays top-level
    # (it configures the query pipeline, not an ingest stage), exactly as today.
    _STAGE_CONFIG_KEYS: ClassVar[tuple[str, ...]] = (
        "parse", "enrich", "chunk", "contextualize", "metagen", "embed",
    )

    @property
    def stages(self) -> dict[str, dict[str, Any]]:
        """
        Keyed-map view of the per-stage config blocks (the new dynamic-assembler shape).

        Read-only and NOT a stored Pydantic field: the flat fields above remain the canonical
        storage shape so the discovery config_describer (which walks the model's flat fields) and
        every existing direct-dict reader are unaffected. The dynamic assembler can consume either
        the flat reads (``cfg.parse``) or this keyed view.

        Returns:
            dict[str, dict[str, Any]]: ``{stage_config_key: <block as JSON dict>}``.
        """
        return {key: getattr(self, key).model_dump(mode="json") for key in self._STAGE_CONFIG_KEYS}

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> PipelineConfig:
        """
        Build a PipelineConfig from a (possibly empty/partial) JSON dict — accepts BOTH shapes.

        Two storage shapes are read transparently:
          * Old FLAT shape (every ``collection.pipeline`` stored today):
            ``{"parse": {...}, "enrich": {...}, ..., "search": {...}}`` — passed through unchanged.
          * New KEYED shape: ``{"stages": {"parse": {...}, ...}, "search": {...}}`` — the per-stage
            blocks are un-nested back to the flat fields before validation.
        An empty/None dict falls back to defaults; a partial dict fills the rest from defaults.

        Args:
            raw (dict | None): Serialized config (collection.pipeline jsonb or request body).

        Returns:
            PipelineConfig: Parsed config with defaults filled in.
        """
        # 1. Empty / None → all defaults.
        if not raw:
            return cls()

        # 2. New keyed shape → un-nest the per-stage blocks into the flat fields (search stays top).
        if isinstance(raw, dict) and isinstance(raw.get("stages"), dict):
            flat: dict[str, Any] = {**raw["stages"]}
            if "search" in raw:
                flat["search"] = raw["search"]
            return cls.model_validate(flat)

        # 3. Old flat shape → validate directly (back-compat for every stored config today).
        return cls.model_validate(raw)

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize to the canonical (flat) JSON dict for collection.pipeline storage.

        Kept in the flat shape so storage stays byte-compatible with every config persisted today
        and the discovery describer / reindex-diff / direct-dict readers are untouched. ``from_dict``
        additionally accepts the keyed shape, so a config authored either way round-trips.
        """
        return self.model_dump(mode="json")

    def redacted_dict(self) -> dict[str, Any]:
        """
        Serialize with all credential params masked -- safe to echo to clients and logs.

        Returns:
            dict: The config with secret provider params replaced by "***".
        """
        return _redact(self.model_dump(mode="json"))


def build_default_pipeline(cfg: Any) -> PipelineConfig:
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
    # Lazy imports -- triggered only when this function is actually called (after providers
    # register themselves), not at module load time.  Preserves the leaf constraint.
    from common_libs.providers.classifier.layout_labels.config import LayoutLabelsConfig
    from common_libs.providers.embed.bge_server.config import BgeServerEmbedConfig
    from common_libs.providers.parser.docling import DoclingConfig

    # 1. Parser chain
    # GPU usage is a deployment decision resolved from DOCLING_USE_GPU via merge_defaults()
    # at assembly time — NOT a per-collection pipeline field, so it is not set here.
    parse_cfg = ParseConfig(chain=[DoclingConfig()])

    # 2. Figure classifier chain
    # Default deployment stack uses the heuristic layout-labels classifier; a per-collection
    # config swaps in vit_onnx (with its own model_path) when needed.
    classifier_chain: list = [LayoutLabelsConfig()]

    # 3. OCR chain — empty by default; OCR providers are opted in per-collection.
    ocr_chain: list = []

    # 4. VLM chain — empty by default (disabled); VLM is opted in per-collection.
    vlm_chain: list = []

    # OCR gate inherits the legacy threshold (default 0.85 if not present).
    ocr_threshold = float(getattr(cfg, "OCR_CONFIDENCE_THRESHOLD", 0.85))

    enrich_cfg = EnrichConfig(
        classifier_chain=classifier_chain,
        ocr_chain=ocr_chain,
        ocr_gate=ChainGateConfig(min_score=ocr_threshold),
        vlm_chain=vlm_chain,
    )

    # 5. Chunking — split_method is a plain spec dict (the builder's adapter types it at build time).
    chunk_cfg = ChunkConfig(
        split_method={
            "id": "token_budget",
            "max_tokens": getattr(cfg, "CHUNK_MAX_TOKENS", 512),
            "overlap_blocks": getattr(cfg, "CHUNK_OVERLAP_BLOCKS", 0),
        }
    )

    # 6. Embedding chain
    # bge_server is the default embed provider (BGE-M3 dense+sparse, local). base_url / batch_size
    # are per-collection — BgeServerEmbedConfig structural defaults apply here.
    embed_cfg = EmbedConfig(chain=[BgeServerEmbedConfig()])

    # 7. S5b metagen — always empty in the default stack (a complete no-op): the provider chain +
    #    targets are per-collection config. METAGEN_ENABLED acts as a deployment kill-switch and the
    #    budget cap (METAGEN_MAX_BUDGET_USD) is threaded into the stage where it is actually built
    #    (ProviderRegistry, which holds RUNTIME_CONFIG) — neither has any effect on this empty default.
    metagen_cfg = MetaGenConfig()

    return PipelineConfig(
        parse=parse_cfg, enrich=enrich_cfg, chunk=chunk_cfg, metagen=metagen_cfg, embed=embed_cfg,
    )

