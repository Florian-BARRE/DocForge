# ====== Code Summary ======
# ImportContentSparse — the import-side guard against a hidden sparse-encoder mismatch. The import
# declares the new store from the CONFIG layout, so bundle content sparse vectors encoded by another
# provider would land under the "right" modifier and become undetectable (a later rebuild would copy
# them). When the bundle cannot vouch for them — the source collection was flagged needs_reindex, or its
# embed baseline's sparse half is unknown or differs from the config — each restored batch's
# ``content_bm25`` is re-encoded from the restored chunk text through the configured sparse provider.
# Best-effort, like the meta lexical re-encode: on a provider failure the remaining points keep their
# bundle vectors, the collection is flagged needs_reindex (rebuild_index repairs it) and the import
# never fails.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.build.validation_message import ValidationMessage
from shared_libs.services.db.facades import CollectionTransferFacade
from shared_libs.services.db.facades.content_sparse_reencoder import ContentSparseReencoder
from shared_libs.services.db.index_embed_baseline import EmbedBaseline
from shared_libs.services.db.qdrant import QdrantPoint, VectorNames

# ====== Local Project Imports ======
from ..manifest import CollectionContractModel


class ImportContentSparse(LoggerClass):
    """Re-encode the bundle's content sparse vectors when it cannot vouch for their encoder."""

    def __init__(self, facade: CollectionTransferFacade, collection_id: uuid.UUID) -> None:
        """
        Args:
            facade (CollectionTransferFacade): The store gateway (re-encoder + flag write).
            collection_id (uuid.UUID): The new imported collection.
        """
        LoggerClass.__init__(self)
        self._facade = facade
        self._collection_id = collection_id
        self._reencoder: ContentSparseReencoder | None = None
        self._failed = False
        self.reencoded = 0

    @staticmethod
    def needed(contract: CollectionContractModel) -> bool:
        """Whether the bundle's content sparse vectors cannot be trusted as the configured encoder's.

        Args:
            contract (CollectionContractModel): The bundle's collection contract.

        Returns:
            bool: True when the source was flagged needs_reindex, or its embed baseline's sparse half
                is unknown (older bundle) or differs from the bundle's own embed config.
        """
        return contract.needs_reindex or not EmbedBaseline.sparse_matches(
            contract.indexed_embed_signature, contract.pipeline
        )

    async def prepare(self) -> None:
        """Build the configured sparse provider's re-encoder (none when the config has no sparse)."""
        try:
            self._reencoder = await self._facade.content_sparse_reencoder(self._collection_id)
        except Exception as exc:  # noqa: BLE001 — best-effort: the bundle vectors are kept.
            self.__fail(exc)

    def __fail(self, exc: Exception) -> None:
        """Stop re-encoding: later batches keep their bundle vectors (logged input-free)."""
        self._failed = True
        self._reencoder = None
        self.logger.warning(
            f"Content sparse re-encode failed on import of {self._collection_id} "
            f"({type(exc).__name__}: {ValidationMessage.describe(exc)}) — the bundle's vectors are "
            f"kept and the collection is flagged needs_reindex (run rebuild_index)"
        )

    async def apply(self, batch: list[QdrantPoint]) -> None:
        """Replace each point's content sparse vector by its re-encoding (in place, best-effort)."""
        if self._reencoder is None or not batch:
            return
        try:
            encoded = await self._reencoder.encode([point.point_id for point in batch])
        except Exception as exc:  # noqa: BLE001 — best-effort: the bundle vectors are kept.
            self.__fail(exc)
            return
        content = VectorNames.CONTENT_SPARSE
        for point in batch:
            vector = encoded.get(point.point_id, {}).get(content)
            if vector is None:
                point.sparse.pop(content, None)
            else:
                point.sparse[content] = vector
                self.reencoded += 1

    async def finish(self) -> None:
        """Flag the collection needs_reindex when the re-encode did not complete."""
        if self._failed:
            await self._facade.flag_needs_reindex(self._collection_id)
        elif self.reencoded:
            self.logger.info(
                f"Re-encoded the content sparse vector of {self.reencoded} point(s) on import of "
                f"{self._collection_id} through the configured sparse provider"
            )


__all__ = ["ImportContentSparse"]
