# ====== Code Summary ======
# Collections sub-API: list / create / delete (/api/v1/collections).

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .transport import DocForgeTransport


class CollectionsApi(LoggerClass):
    """Collection lifecycle endpoints."""

    def __init__(self, transport: DocForgeTransport) -> None:
        """Bind the shared transport.

        Args:
            transport (DocForgeTransport): The shared HTTP transport.
        """
        LoggerClass.__init__(self)
        self._t = transport

    async def list(self) -> Any:
        """List all collections (newest first)."""
        return await self._t.get("/collections/list")

    async def create(
        self,
        name: str,
        supported_formats: list[str] | None = None,
        max_file_size_bytes: int | None = None,
        locality_policy: str | None = None,
        embedding_model: str | None = None,
        unknown_field_policy: str | None = None,
        pipeline: dict[str, Any] | None = None,
        metadata_schema: list[dict[str, Any]] | None = None,
    ) -> Any:
        """
        Create a collection. Only ``name`` is required; omitted knobs use server defaults.

        Args:
            name (str): Human-readable collection name (unique).
            supported_formats (list[str] | None): Accepted extensions (e.g. ["pdf", "docx"]).
            max_file_size_bytes (int | None): Per-file size cap.
            locality_policy (str | None): "on_premise_only" or "external_allowed".
            embedding_model (str | None): Embedding model id (default "BAAI/bge-m3").
            unknown_field_policy (str | None): "reject" | "ignore" | "store".
            pipeline (dict | None): Partial/full pipeline config; defaults fill the rest.
            metadata_schema (list[dict] | None): Custom metadata field specs.

        Returns:
            Any: The resolved config state (with an ``applied`` transparency envelope).
        """
        # 1. Send only the fields the caller actually provided so server defaults apply
        body: dict[str, Any] = {"name": name}
        optional = {
            "supported_formats": supported_formats,
            "max_file_size_bytes": max_file_size_bytes,
            "locality_policy": locality_policy,
            "embedding_model": embedding_model,
            "unknown_field_policy": unknown_field_policy,
            "pipeline": pipeline,
            "metadata_schema": metadata_schema,
        }
        body.update({k: v for k, v in optional.items() if v is not None})

        # 2. Create
        return await self._t.post("/collections/create", body)

    async def delete(self, collection_id: str) -> Any:
        """
        Delete a collection and all associated data (Postgres + Qdrant + non-shared S3 blobs).

        Args:
            collection_id (str): UUID of the collection to delete.

        Returns:
            Any: Deletion acknowledgement.
        """
        return await self._t.delete(f"/collections/{collection_id}/delete")
