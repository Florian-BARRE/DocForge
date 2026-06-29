# ====== Code Summary ======
# The PipelineBuilder's input contract — the discovery-aligned shape the builder consumes (Option B):
# exactly what describe() lays out (per-node Config values + per-chain provider specs + gate), plus
# the collection-derived metagen bits and the live infra clients. A DB row of saved per-collection
# config is parsed into an IngestBuildSpec by a (future) adapter; for now tests construct it directly.

# ====== Standard Library Imports ======
from dataclasses import dataclass, field
from typing import Any

# ====== Internal Project Imports ======
from common_libs.config.pipeline.chain_gate_config import ChainGateConfig
from common_libs.pipelines import NodeConfig


@dataclass(slots=True)
class ChainSpec:
    """
    One category's saved chain config: an ordered list of provider specs + the escalation gate.

    Attributes:
        specs (list[Any]): Ordered provider config specs (each a ``@register`` provider config).
            Empty = a no-op chain (the capability is disabled).
        gate (ChainGateConfig): Escalation + exhaustion policy for this chain.
    """

    specs: list[Any] = field(default_factory=list)
    gate: ChainGateConfig = field(default_factory=ChainGateConfig)


@dataclass(slots=True)
class IngestClients:
    """
    The live infra handles the builder registers as services (used directly — no Protocol port).

    Attributes:
        object_store (Any): S3Client (SeaweedFS, content-addressed blobs).
        converter (Any): The office/HTML -> PDF converter (Gotenberg) used by the ingest stage; an
            infra service (one deployment URL), not a per-collection chain.
        qdrant (Any): QdrantStorageClient (vector upserts).
        postgres (Any): PostgresClient (session factory, source of truth).
        serializer (Any): MarkdownSerializer (the parse markdown view).
        provider_cache (Any): ProviderCallCache (cross-document provider-call cache).
    """

    object_store: Any
    converter: Any
    qdrant: Any
    postgres: Any
    serializer: Any
    provider_cache: Any


@dataclass(slots=True)
class IngestBuildSpec:
    """
    The full discovery-aligned config the builder turns into a live ingest pipeline.

    Attributes:
        chains (dict[str, ChainSpec]): Per-category chain config, keyed by provider category
            (``parser`` / ``classifier`` / ``ocr`` / ``vlm`` / ``llm`` / ``embed``). A missing
            category builds an empty (no-op) chain.
        configs (dict[str, NodeConfig]): Per-stage node Config values, keyed by stage key
            (``enrich`` / ``chunk`` / ``contextualize`` / ``metagen`` / ``embed_index``). A missing
            key uses the stage's default Config.
        metagen_targets (list[Any]): The metagen field bindings ``{field, prompt, scope}`` (derived
            from the collection metadata schema). Empty = metagen no-op.
        metagen_field_types (dict[str, Any]): Generated-field type lookup (collection-derived).
    """

    chains: dict[str, ChainSpec] = field(default_factory=dict)
    configs: dict[str, NodeConfig] = field(default_factory=dict)
    metagen_targets: list[Any] = field(default_factory=list)
    metagen_field_types: dict[str, Any] = field(default_factory=dict)


__all__ = ["ChainSpec", "IngestClients", "IngestBuildSpec"]
