# ====== Code Summary ======
# IngestBuildSpecAdapter - converts a STORED per-collection PipelineConfig into the builder's typed
# IngestBuildSpec input. It splits the stored config into three parts:
#   (a) the six provider CHAINS (parser / classifier / ocr / vlm / llm / embed), reusing the already
#       typed @register provider config instances verbatim (no provider conversion);
#   (b) the per-stage NODE Configs (enrich / chunk / contextualize / metagen / embed_index) built from
#       the stored KNOB fields - converting the old chunk HeadingRule / AtomicConfig / split_method into
#       their new co-located equivalents via a field-filtered dict round-trip - and omitting any stage
#       whose config equals the stage default (the builder defaults an absent key);
#   (c) the metagen targets (used as-is) + the generated-field type lookup ported from the old assembler.
# NOTE - sparse deferral: EmbedConfig.sparse has no separate slot in the single new ``embed`` ChainSpec.
# It is intentionally NOT mapped here; sparse handling is deferred (the embed provider config itself may
# already carry dense + sparse). The adapter does not break on a populated ``sparse`` - it is ignored.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from common_libs.config.pipeline.pipeline import PipelineConfig
from common_libs.domain.metadata.meta_field_spec import MetaFieldSpec
from common_libs.pipelines import NodeConfig
from common_libs.pipelines.core.ingest.stages.chunk.config import (
    AtomicConfig,
    HeadingRule,
    IngestStageChunkConfig,
    IngestStageChunkSplitSemanticConfig,
    IngestStageChunkSplitSentenceWindowConfig,
    IngestStageChunkSplitTokenBudgetConfig,
)
from common_libs.pipelines.core.ingest.stages.contextualize.config import (
    IngestStageContextualizeConfig,
)
from common_libs.pipelines.core.ingest.stages.embed_index.config import IngestStageEmbedIndexConfig
from common_libs.pipelines.core.ingest.stages.enrich.config import IngestStageEnrichConfig
from common_libs.pipelines.core.ingest.stages.metagen.config import IngestStageMetagenConfig

# ====== Local Project Imports ======
from .models import ChainSpec, IngestBuildSpec


class IngestBuildSpecAdapter:
    """
    Translate a stored ``PipelineConfig`` into the builder's typed ``IngestBuildSpec``.

    Static-only: the adapter carries no state, it is a pure config-shape transformation. The single
    entry point is ``from_pipeline_config``. Provider config instances inside the stored chains are
    reused verbatim (they are the same ``@register`` configs the builder's ChainBuilder expects), so
    only the per-stage knob blocks and the metagen field lookup are actually converted.
    """

    logger = loggerplusplus.bind(identifier="IngestBuildSpecAdapter")

    # Map each split-method discriminator id to its NEW co-located config class. The old stored
    # split_method shares the same ``id`` + field names, so a field-filtered dict round-trip rebuilds
    # the matching new variant (and drops keys the strict new model forbids, e.g. semantic's ``embed``).
    _SPLIT_VARIANTS: dict[str, type] = {
        "token_budget": IngestStageChunkSplitTokenBudgetConfig,
        "sentence_window": IngestStageChunkSplitSentenceWindowConfig,
        "semantic": IngestStageChunkSplitSemanticConfig,
    }

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation - the adapter is a static-only transformation."""
        raise TypeError("IngestBuildSpecAdapter is a static-only class and cannot be instantiated.")

    @staticmethod
    def __filtered(model_cls: type, source: dict[str, Any]) -> dict[str, Any]:
        """
        Keep only the keys ``model_cls`` declares as fields.

        Args:
            model_cls (type): The target Pydantic model.
            source (dict): A ``model_dump()`` of the source model (may carry extra keys).

        Returns:
            dict: ``source`` restricted to ``model_cls``'s field names (strict models forbid extras).
        """
        return {key: value for key, value in source.items() if key in model_cls.model_fields}

    @classmethod
    def __convert_split_method(cls, old_split: Any) -> Any:
        """
        Convert a stored split_method into its new co-located equivalent.

        Args:
            old_split (Any): The stored ``split_method`` spec — a plain dict (the storage shape,
                discriminated by ``id``); a typed model is also accepted defensively.

        Returns:
            Any: The matching ``IngestStageChunkSplit*Config`` instance.

        Raises:
            KeyError: If the stored split_method carries an unknown discriminator id.
        """
        # 1. Normalise to a dict, then pick the new variant by its discriminator id.
        dumped = old_split if isinstance(old_split, dict) else old_split.model_dump()
        variant_cls = cls._SPLIT_VARIANTS[dumped["id"]]

        # 2. Rebuild the new variant from only the fields it accepts (drops forbidden extras).
        return variant_cls(**cls.__filtered(variant_cls, dumped))

    @classmethod
    def __build_chunk_config(cls, chunk: Any) -> IngestStageChunkConfig:
        """
        Build the new chunk node config from the stored ``ChunkConfig`` knobs.

        Args:
            chunk (Any): The stored ``ChunkConfig`` block.

        Returns:
            IngestStageChunkConfig: The converted chunk config.
        """
        # 1. Convert the supporting models (heading rules + atomic policy) via field-filtered round-trip.
        heading_rules = [
            HeadingRule(**cls.__filtered(HeadingRule, rule.model_dump()))
            for rule in chunk.heading_rules
        ]
        atomic = AtomicConfig(**cls.__filtered(AtomicConfig, chunk.atomic.model_dump()))

        # 2. Assemble the chunk config, converting the discriminated split_method choice.
        return IngestStageChunkConfig(
            heading_rules=heading_rules,
            merge_short_sections=chunk.merge_short_sections,
            reinject_breadcrumb=chunk.reinject_breadcrumb,
            split_method=cls.__convert_split_method(chunk.split_method),
            hierarchical=chunk.hierarchical,
            atomic=atomic,
            cross_references=chunk.cross_references,
        )

    @staticmethod
    def __embed_batch_size(embed: Any) -> int | None:
        """
        Resolve the embed batch size from the first stored provider that declares one.

        ``EmbedConfig`` has no top-level batch_size: it lives on the provider config (e.g.
        ``BgeServerEmbedConfig.batch_size``). The new ``embed_index`` stage batches at a single
        ``embed_batch_size``, so the first chain provider's value is the faithful source.

        Args:
            embed (Any): The stored ``EmbedConfig`` block.

        Returns:
            int | None: The provider batch size, or None when no provider declares one.
        """
        for provider in embed.chain:
            batch_size = getattr(provider, "batch_size", None)
            if batch_size is not None:
                return int(batch_size)
        return None

    @classmethod
    def __build_configs(cls, config: PipelineConfig) -> dict[str, NodeConfig]:
        """
        Build the per-stage node Configs, omitting any stage whose config equals the stage default.

        Args:
            config (PipelineConfig): The stored per-collection config.

        Returns:
            dict[str, NodeConfig]: ``stage_key -> NodeConfig`` for every non-default stage.
        """
        # 1. Build one candidate config per stage from the stored knob fields.
        budget = float(getattr(config.metagen, "max_budget_usd", 0.0))
        batch_size = cls.__embed_batch_size(config.embed)
        candidates: dict[str, NodeConfig] = {
            "enrich": IngestStageEnrichConfig(chart_to_data=config.enrich.chart_to_data),
            "chunk": cls.__build_chunk_config(config.chunk),
            "contextualize": IngestStageContextualizeConfig(
                include_doc_title=config.contextualize.include_doc_title,
                include_breadcrumb=config.contextualize.include_breadcrumb,
                breadcrumb_separator=config.contextualize.breadcrumb_separator,
                header_body_separator=config.contextualize.header_body_separator,
            ),
            "metagen": IngestStageMetagenConfig(
                max_concurrency=config.metagen.max_concurrency,
                max_budget_usd=budget,
            ),
        }
        if batch_size is not None:
            candidates["embed_index"] = IngestStageEmbedIndexConfig(embed_batch_size=batch_size)

        # 2. Keep only the stages that differ from their default (the builder defaults the rest).
        return {
            key: value
            for key, value in candidates.items()
            if value != type(value)()
        }

    @staticmethod
    def __resolve_field_types(
        metadata_fields: list[Any] | None,
        targets: list[Any],
    ) -> dict[str, MetaFieldSpec]:
        """
        Build the type/enum lookup for the generated fields a metagen target references.

        Ported from the old assembler: only fields authored as ``origin == "generated"`` AND bound by a
        target are kept - the metagen stage must never write into a system/user field. Accepts both dict
        snapshots (the worker passes plain dicts, decoupled from the ORM session) and ORM rows.

        Args:
            metadata_fields (list | None): The collection's metadata field specs.
            targets (list): The configured metagen targets.

        Returns:
            dict[str, MetaFieldSpec]: ``field_name -> MetaFieldSpec`` for the eligible generated fields.
        """
        # 1. Nothing to resolve without both fields and targets.
        if not metadata_fields or not targets:
            return {}

        def _attr(obj: Any, name: str, default: Any = None) -> Any:
            return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)

        # 2. Keep only generated fields that a target actually binds.
        target_names = {target.field for target in targets}
        field_types: dict[str, MetaFieldSpec] = {}
        for field in metadata_fields:
            name = _attr(field, "field_name")
            if not name or name not in target_names or _attr(field, "origin") != "generated":
                continue
            field_types[name] = MetaFieldSpec(
                field_name=name,
                field_type=_attr(field, "field_type", "string"),
                enum_values=_attr(field, "enum_values"),
                required=bool(_attr(field, "required", False)),
                origin="generated",
            )
        return field_types

    @classmethod
    def __build_chains(cls, config: PipelineConfig) -> dict[str, ChainSpec]:
        """
        Build the six per-category ChainSpecs from the stored chain + gate fields.

        Provider config instances are reused verbatim (the same ``@register`` configs the builder's
        ChainBuilder consumes), so each ChainSpec only pairs the stored ordered specs with the matching
        stored escalation gate. ``EmbedConfig.sparse`` is intentionally not mapped (sparse deferral).

        Args:
            config (PipelineConfig): The stored per-collection config.

        Returns:
            dict[str, ChainSpec]: ``category -> ChainSpec`` for all six chain categories.
        """
        enrich = config.enrich
        return {
            "parser": ChainSpec(specs=list(config.parse.chain), gate=config.parse.gate),
            "classifier": ChainSpec(specs=list(enrich.classifier_chain), gate=enrich.classifier_gate),
            "ocr": ChainSpec(specs=list(enrich.ocr_chain), gate=enrich.ocr_gate),
            "vlm": ChainSpec(specs=list(enrich.vlm_chain), gate=enrich.vlm_gate),
            "llm": ChainSpec(specs=list(config.metagen.chain), gate=config.metagen.gate),
            "embed": ChainSpec(specs=list(config.embed.chain), gate=config.embed.gate),
        }

    @classmethod
    def from_pipeline_config(
        cls,
        config: PipelineConfig,
        metadata_fields: list[Any] | None = None,
    ) -> IngestBuildSpec:
        """
        Convert a stored ``PipelineConfig`` into the builder's typed ``IngestBuildSpec``.

        Args:
            config (PipelineConfig): The stored per-collection pipeline config.
            metadata_fields (list | None): The collection's metadata field specs (dicts or ORM rows),
                used to resolve the generated-field type lookup. None/empty -> no field types.

        Returns:
            IngestBuildSpec: The discovery-aligned config the ``IngestPipelineBuilder`` consumes.
        """
        # 1. Split the stored config into chains, per-stage node Configs, and the metagen bits.
        chains = cls.__build_chains(config)
        configs = cls.__build_configs(config)
        targets = list(config.metagen.targets)
        field_types = cls.__resolve_field_types(metadata_fields, config.metagen.targets)

        # 2. Assemble the spec and trace the resulting shape for observability.
        cls.logger.debug(
            f"Adapted PipelineConfig -> IngestBuildSpec: {len(chains)} chains, "
            f"{len(configs)} node configs, {len(targets)} metagen targets, "
            f"{len(field_types)} generated field types."
        )
        return IngestBuildSpec(
            chains=chains,
            configs=configs,
            metagen_targets=targets,
            metagen_field_types=field_types,
        )


__all__ = ["IngestBuildSpecAdapter"]
