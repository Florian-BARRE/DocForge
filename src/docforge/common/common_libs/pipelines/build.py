# ====== Code Summary ======
# FlowPipelineBuilder — turns a saved per-collection PipelineConfig into a live flow pipeline (a
# GroupNode of the 7 stages) + its ServiceRegistry, ready for FlowEngine.run. It reuses the config
# adapter (chain specs + node configs + metagen bits) and the ChainBuilder; the parser providers
# become parser NODES (the parse escalation candidates), while the figure/llm/embed providers are
# built into chains injected as services. No hardcoded endpoints: provider config comes from the
# stored config, deployment defaults from the passed-in defaults_cfg (RUNTIME_CONFIG).

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from common_libs.config.pipeline.chain_gate_config import ChainGateConfig
from common_libs.pipelines.builder import ChainBuilder, IngestBuildSpecAdapter, IngestClients
from common_libs.pipelines.chunk import ChunkStage
from common_libs.pipelines.contextualize import ContextualizeStage
from common_libs.pipelines.embed_index import EmbedIndexStage
from common_libs.pipelines.enrich import EnrichStage
from common_libs.pipelines.flow import GroupNode, ServiceRegistry, Transition
from common_libs.pipelines.ingest import IngestStage
from common_libs.pipelines.metagen import MetagenStage
from common_libs.pipelines.parse import ParseStage
from common_libs.pipelines.parse.nodes.docling import DoclingParse

# Map a parser provider id -> its clean ActionNode candidate of the parse escalation.
_PARSER_NODES: dict[str, type] = {"docling": DoclingParse}

# The figure / LLM / embed providers are injected as chain SERVICES (not parse-style nodes).
_SERVICE_CHAINS = ("classifier", "ocr", "vlm", "llm", "embed")

# The 7 stages, in pipeline order (the flow wires them with ``always`` edges).
_STAGE_ORDER = ("ingest", "parse", "enrich", "chunk", "contextualize", "metagen", "embed_index")


class FlowPipelineBuilder(LoggerClass):
    """Build a live flow ingest pipeline + service registry from a saved per-collection config."""

    def __init__(self, defaults_cfg: Any = None) -> None:
        """
        Args:
            defaults_cfg (Any): Deployment config supplying env-level provider defaults (GPU flags…).
        """
        LoggerClass.__init__(self)
        self._chain_builder = ChainBuilder(defaults_cfg)
        self._defaults = defaults_cfg

    def build(
        self, config: Any, clients: IngestClients, metadata_fields: list | None = None
    ) -> tuple[GroupNode, ServiceRegistry]:
        """
        Build the flow ingest pipeline + its service registry from a stored config.

        Args:
            config (Any): The collection's stored PipelineConfig.
            clients (IngestClients): The live infra handles registered as services.
            metadata_fields (list | None): The collection metadata schema (feeds metagen).

        Returns:
            tuple[GroupNode, ServiceRegistry]: The pipeline group + the service registry.
        """
        # 1. Adapt the stored config into chain specs + node configs + metagen bits.
        spec = IngestBuildSpecAdapter.from_pipeline_config(config, metadata_fields)

        # 2. Build the figure/llm/embed chains (injected services) + the parser nodes (parse candidates).
        chains = self.__build_chains(spec)
        parsers = self.__build_parsers(spec)

        # 3. Instantiate + wire the stages, then register the services.
        stages = self.__build_stages(spec, chains, parsers)
        transitions = [
            Transition(_STAGE_ORDER[i], _STAGE_ORDER[i + 1]) for i in range(len(_STAGE_ORDER) - 1)
        ]
        pipeline = GroupNode("ingest_pipeline", stages, transitions)
        registry = self.__registry(chains, clients)
        self.logger.info(f"Built flow ingest pipeline: {len(stages)} stages, {len(parsers)} parser(s).")
        return pipeline, registry

    def __build_chains(self, spec: Any) -> dict[str, Any]:
        """Build each figure/llm/embed category's chain (empty when omitted), keyed by category."""
        chains: dict[str, Any] = {}
        for category in _SERVICE_CHAINS:
            chain_spec = spec.chains.get(category)
            specs = chain_spec.specs if chain_spec else []
            gate = chain_spec.gate if chain_spec else ChainGateConfig()
            chains[category] = self._chain_builder.build(category, specs, gate)
        return chains

    def __build_parsers(self, spec: Any) -> list:
        """Build the parser escalation candidates from the parser spec (defaults to Docling)."""
        parser_spec = spec.chains.get("parser")
        specs = parser_spec.specs if parser_spec else []
        parsers: list = []
        for provider in specs:
            node_cls = _PARSER_NODES.get(getattr(provider, "id", ""))
            if node_cls is None:
                continue
            merged = provider.merge_defaults(self._defaults)
            parsers.append(node_cls(node_id=getattr(provider, "id"), use_gpu=getattr(merged, "_use_gpu", False)))
        return parsers or [DoclingParse()]

    def __build_stages(self, spec: Any, chains: dict[str, Any], parsers: list) -> list:
        """Instantiate the 7 stages with their config + the built parsers/chain-derived flags."""
        cfg = spec.configs
        enrich_cfg = cfg.get("enrich")
        chart_to_data = bool(getattr(enrich_cfg, "chart_to_data", False)) if enrich_cfg else False
        metagen_cfg = cfg.get("metagen")
        return [
            IngestStage(),
            ParseStage(parsers, accept_threshold=0.8),
            EnrichStage(
                ocr_enabled=bool(chains["ocr"].providers),
                vlm_enabled=bool(chains["vlm"].providers),
                chart_to_data=chart_to_data,
            ),
            ChunkStage(),
            ContextualizeStage(),
            MetagenStage(
                targets=spec.metagen_targets,
                field_types=spec.metagen_field_types,
                max_concurrency=getattr(metagen_cfg, "max_concurrency", 8) if metagen_cfg else 8,
                max_budget_usd=getattr(metagen_cfg, "max_budget_usd", 0.0) if metagen_cfg else 0.0,
            ),
            EmbedIndexStage(),
        ]

    def __registry(self, chains: dict[str, Any], clients: IngestClients) -> ServiceRegistry:
        """Register the built chains (as ``<category>_chain``) + the infra clients as services."""
        items: dict[str, Any] = {
            "object_store": clients.object_store,
            "converter": clients.converter,
            "qdrant": clients.qdrant,
            "postgres": clients.postgres,
            "serializer": clients.serializer,
            "provider_cache": clients.provider_cache,
        }
        for category, chain in chains.items():
            items[f"{category}_chain"] = chain
        return ServiceRegistry(items=items)


__all__ = ["FlowPipelineBuilder"]
