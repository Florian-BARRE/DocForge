# ====== Code Summary ======
# S6Builder — static helper that constructs a per-run S6EmbedIndexStage from the
# collection's embed provider configuration (EmbedConfig discriminated union).
# Extracted from StageEngine._build_s6_from_config to keep the engine core focused
# on orchestration and isolate provider-dispatch logic here.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from libs.core.contracts.pipeline_config import EmbedConfig
    from libs.engine.assembly import ProviderRegistry

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

from libs.data.storage.postgres.repositories import ChunkRepository
from libs.data.storage.qdrant.client import QdrantStorageClient

# ====== Internal Project Imports ======
from libs.engine.stages.s6_embed_index import S6EmbedIndexStage


class S6Builder:
    """
    Static helper to construct a per-run S6EmbedIndexStage from an EmbedConfig.

    Dispatch is handled by a Pydantic discriminated union: the ``embed.provider``
    field resolves to one of the three typed config objects, each of which exposes
    a ``.build()`` method that instantiates the matching provider:

    - ``TeiEmbedConfig``          (``id="tei"``)           → local TEI/BGE-M3, dense + BM25 sparse
    - ``LocalOpenAIEmbedConfig``  (``id="openai_compat"``) → local OpenAI-compat server, dense-only
    - ``OpenAIEmbedConfig``       (``id="openai"``)        → external cloud API, api_key required

    Returns ``None`` when infrastructure (Qdrant or chunk repo) is unavailable.
    """

    logger = loggerplusplus.bind(identifier="S6Builder")

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        raise TypeError("S6Builder is a static-only class and cannot be instantiated.")

    @classmethod
    def build(
        cls,
        embed: EmbedConfig,
        qdrant: QdrantStorageClient | None,
        chunk_repo: ChunkRepository | None,
        registry: ProviderRegistry | None,
    ) -> S6EmbedIndexStage | None:
        """
        Build a per-run S6 stage from the collection's embed provider config.

        Returns ``None`` when infrastructure (Qdrant or chunk repo) is unavailable —
        the caller raises a ``RuntimeError`` if ``collection_id`` is set (see ``StageEngine.run()``).

        Args:
            embed (EmbedConfig): Collection-level embed configuration (typed provider spec).
            qdrant (QdrantStorageClient | None): Live Qdrant client, or None when unavailable.
            chunk_repo (ChunkRepository | None): Chunk persistence, or None when unavailable.
            registry (ProviderRegistry | None): Provider registry used to build the embed chain.

        Returns:
            S6EmbedIndexStage | None: A ready S6 stage, or None when infrastructure is missing.
        """
        # 1. Guard: infrastructure must be present to build S6
        if qdrant is None or chunk_repo is None:
            return None

        # 2. Build the embed chain — via registry (preferred) or direct spec.build() fallback
        embed_chain, batch_size = cls._build_embed_chain(embed, registry)
        if embed_chain is None:
            return None

        # 3. Construct and return the S6 stage
        return S6EmbedIndexStage(
            embed_chain=embed_chain,
            qdrant=qdrant,
            chunk_repo=chunk_repo,
            embed_batch_size=batch_size,
        )

    @classmethod
    def _build_embed_chain(
        cls,
        embed: EmbedConfig,
        registry: ProviderRegistry | None,
    ) -> tuple[Any, int]:
        """
        Build the embed chain and extract the batch size from the config.

        When a registry is available, delegates to ``registry._build_embed_chain`` so every
        provider in the chain is subject to the same availability + credential checks the
        other stages enforce.  Falls back to a single ``spec.build()`` call when no registry.

        Args:
            embed (EmbedConfig): Collection-level embed configuration.
            registry (ProviderRegistry | None): Provider registry, or None for legacy callers.

        Returns:
            tuple[Any, int]: (embed_chain, batch_size) — chain is None when embed.chain is empty.
        """
        if registry is not None:
            # Registry path: full chain with gate + availability checks
            embed_chain = registry._build_embed_chain(embed.chain, embed.gate)
            first_spec = embed.chain[0] if embed.chain else None
            batch_size: int = getattr(first_spec, "batch_size", 32)
            return embed_chain, batch_size

        # Legacy fallback: treat the first chain entry as the single provider
        if not embed.chain:
            return None, 32
        spec = embed.chain[0]
        embed_provider = spec.build()
        batch_size = getattr(spec, "batch_size", 32)
        from libs.capabilities.chain import Chain
        from libs.capabilities.chain_gate import ChainGate
        embed_chain = Chain(stage="embed", providers=[embed_provider], gate=ChainGate(embed.gate))
        return embed_chain, batch_size
