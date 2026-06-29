# ====== Code Summary ======
# IngestPipelineBuilder — the config->live-pipeline bridge for the ingest pipeline. Given a saved,
# discovery-aligned IngestBuildSpec + the live infra clients, it builds every provider chain, the
# chunk splitter, instantiates the 7 stages with their co-located Config + injected chains/splitter,
# registers all services, and returns a ready (IngestPipeline, ServiceRegistry) for the engine to run.
# The pipeline is rebuilt fresh per run from the stable saved config (it carries live handles, so it
# is never cached as an object).

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from common_libs.pipelines import ServiceRegistry
from common_libs.pipelines.core.ingest import IngestPipeline
from common_libs.pipelines.core.ingest.stages import (
    IngestStageChunk,
    IngestStageContextualize,
    IngestStageEmbedIndex,
    IngestStageEnrich,
    IngestStageIngest,
    IngestStageMetagen,
    IngestStageParse,
)
from common_libs.pipelines.core.ingest.stages.chunk import IngestStageChunkConfig

# ====== Local Project Imports ======
from .chain_builder import ChainBuilder
from .models import ChainSpec, IngestBuildSpec, IngestClients
from .splitter_builder import SplitterBuilder


class IngestPipelineBuilder(LoggerClass):
    """
    Build a live ingest pipeline + its service registry from a saved per-collection config.

    The single entry point is ``build(spec, clients)``. All construction (chains, splitter, stage
    wiring, service registration) is internal; the result is handed straight to the engine.
    """

    # Every chain category the ingest pipeline injects; a category absent from the spec -> empty chain.
    CHAIN_CATEGORIES = ("parser", "classifier", "ocr", "vlm", "llm", "embed")

    def __init__(self, defaults_cfg: object = None) -> None:
        """
        Args:
            defaults_cfg (object): Deployment config supplying env-level provider defaults (GPU flags,
                etc.), threaded to every provider's ``merge_defaults`` / ``availability``. ``None`` is
                safe (every access has a default).
        """
        LoggerClass.__init__(self)
        self._chain_builder = ChainBuilder(defaults_cfg)

    def __build_chains(self, spec: IngestBuildSpec) -> dict[str, object]:
        """
        Build every category's chain (an absent category yields an empty no-op chain, never None).

        Args:
            spec (IngestBuildSpec): The saved config carrying per-category chain specs.

        Returns:
            dict[str, object]: Category -> built Chain, for all CHAIN_CATEGORIES.
        """
        # 1. Build each category in turn, defaulting omitted ones to an empty ChainSpec.
        chains: dict[str, object] = {}
        for category in self.CHAIN_CATEGORIES:
            chain_spec = spec.chains.get(category) or ChainSpec()
            chains[category] = self._chain_builder.build(category, chain_spec.specs, chain_spec.gate)
        return chains

    def __build_stages(
        self,
        spec: IngestBuildSpec,
        chains: dict[str, object],
        chunk_config: IngestStageChunkConfig,
        splitter: object,
    ) -> list:
        """
        Instantiate the 7 ingest stages with their Config + injected chains/splitter.

        Args:
            spec (IngestBuildSpec): The saved config (node Configs + metagen bits).
            chains (dict[str, object]): The built chains by category.
            chunk_config (IngestStageChunkConfig): The resolved chunk config (also drives the splitter).
            splitter (object): The built intra-section splitter for the chunk stage.

        Returns:
            list: The 7 stage instances in declaration order (the engine topo-orders them).
        """
        # 1. Instantiate each stage; parse takes the chain handle (for its node fingerprint), enrich
        #    derives its OCR/VLM enabled flags from whether those chains carry providers.
        cfg = spec.configs
        return [
            IngestStageIngest(),
            IngestStageParse(parser_chain=chains["parser"]),
            IngestStageEnrich(
                config=cfg.get("enrich"),
                ocr_enabled=bool(chains["ocr"].providers),
                vlm_enabled=bool(chains["vlm"].providers),
            ),
            IngestStageChunk(config=chunk_config, splitter=splitter),
            IngestStageContextualize(config=cfg.get("contextualize")),
            IngestStageMetagen(
                targets=spec.metagen_targets,
                field_types=spec.metagen_field_types,
                config=cfg.get("metagen"),
            ),
            IngestStageEmbedIndex(config=cfg.get("embed_index")),
        ]

    def __build_registry(
        self, chains: dict[str, object], clients: IngestClients
    ) -> ServiceRegistry:
        """
        Assemble the service registry: the infra clients + every built chain (as ``<cat>_chain``).

        Args:
            chains (dict[str, object]): The built chains by category.
            clients (IngestClients): The live infra handles.

        Returns:
            ServiceRegistry: The flat registry the engine resolves each node's REQUIRES against.
        """
        # 1. Register the infra clients under their canonical service names.
        items: dict[str, object] = {
            "object_store": clients.object_store,
            "converter": clients.converter,
            "qdrant": clients.qdrant,
            "postgres": clients.postgres,
            "serializer": clients.serializer,
            "provider_cache": clients.provider_cache,
        }
        # 2. Register each chain under its '<category>_chain' service name (e.g. parser -> parser_chain).
        for category, chain in chains.items():
            items[f"{category}_chain"] = chain
        return ServiceRegistry(items=items)

    def build(
        self, spec: IngestBuildSpec, clients: IngestClients
    ) -> tuple[IngestPipeline, ServiceRegistry]:
        """
        Build a live ingest pipeline + service registry from a saved config.

        Args:
            spec (IngestBuildSpec): The discovery-aligned saved config (chains + node Configs + metagen).
            clients (IngestClients): The live infra handles to register as services.

        Returns:
            tuple[IngestPipeline, ServiceRegistry]: Ready to hand to ``PipelineEngine.run``.
        """
        # 1. Build every provider chain (empty no-op chain for any omitted category).
        chains = self.__build_chains(spec)

        # 2. Build the chunk splitter from the chunk config's split_method (semantic borrows embed).
        chunk_config = spec.configs.get("chunk") or IngestStageChunkConfig()
        splitter = SplitterBuilder.build(chunk_config.split_method, chains["embed"])

        # 3. Instantiate the stages, register the services, and compose the pipeline.
        stages = self.__build_stages(spec, chains, chunk_config, splitter)
        registry = self.__build_registry(chains, clients)
        pipeline = IngestPipeline(stages)

        self.logger.info(
            f"Built ingest pipeline: {len(stages)} stages, {len(registry.items)} services."
        )
        return pipeline, registry


__all__ = ["IngestPipelineBuilder"]
