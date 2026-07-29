# ====== Code Summary ======
# Collections sub-API: the contract CRUD under /api/v1/collections — list / get / create
# (full schema + optional pipeline blob) / update (identity, limits, schema diff, config
# blobs) / delete.

from __future__ import annotations

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .transport import DocForgeTransport


class CollectionsApi(LoggerClass):
    """Collection contract endpoints: identity, metadata schema, pipeline/search config blobs."""

    def __init__(self, transport: DocForgeTransport) -> None:
        """
        Bind the shared transport.

        Args:
            transport (DocForgeTransport): The shared HTTP transport.
        """
        LoggerClass.__init__(self)
        self._t = transport

    async def list(self) -> Any:
        """List every collection with its full schema."""
        return await self._t.get("/collections")

    async def get(self, collection_id: str) -> Any:
        """
        Return one collection's full contract.

        Args:
            collection_id (str): The collection's UUID.

        Returns:
            Any: The CollectionModel.
        """
        return await self._t.get(f"/collections/{collection_id}")

    async def create(
        self,
        name: str,
        supported_formats: list[str],
        max_file_size_bytes: int,
        fields: list[dict[str, Any]] | None = None,
        pipeline: dict[str, Any] | None = None,
    ) -> Any:
        """
        Create a collection from A to Z — contract + full schema + pipeline blob.

        Args:
            name (str): Unique human name.
            supported_formats (list[str]): Accepted upload extensions (e.g. ["pdf"]).
            max_file_size_bytes (int): Upload size ceiling, bytes.
            fields (list[dict] | None): The FULL metadata schema, declared up front (each item:
                field_name, field_type, required, filterable, lexical, semantic, enum_values,
                origin, scope). Omitted -> no custom fields.
            pipeline (dict | None): The pipeline blob; omitted -> the product default.

        Returns:
            Any: The created CollectionModel (201).
        """
        # 1. Send only the fields the caller actually provided so server defaults apply
        body: dict[str, Any] = {
            "name": name,
            "supported_formats": supported_formats,
            "max_file_size_bytes": max_file_size_bytes,
        }
        if fields is not None:
            body["fields"] = fields
        if pipeline is not None:
            body["pipeline"] = pipeline
        return await self._t.post("/collections", body)

    async def update(
        self,
        collection_id: str,
        name: str | None = None,
        supported_formats: list[str] | None = None,
        max_file_size_bytes: int | None = None,
        fields: list[dict[str, Any]] | None = None,
        pipeline: dict[str, Any] | None = None,
        search: dict[str, Any] | None = None,
        note: str | None = None,
    ) -> Any:
        """
        Patch identity/limits, the metadata schema (by diff), and/or the config blobs.

        Args:
            collection_id (str): The collection's UUID.
            name (str | None): New unique name.
            supported_formats (list[str] | None): New accepted upload extensions.
            max_file_size_bytes (int | None): New size ceiling, bytes.
            fields (list[dict] | None): The TARGET schema (diffed by field_name; an omitted
                field is removed).
            pipeline (dict | None): New pipeline blob (validated before storage).
            search (dict | None): New search graph blob ({} = stock default).
            note (str | None): Version note shown in the config history.

        Returns:
            Any: The updated CollectionModel.
        """
        # 1. Only send the knobs the caller actually wants to change
        body: dict[str, Any] = {}
        optional = {
            "name": name,
            "supported_formats": supported_formats,
            "max_file_size_bytes": max_file_size_bytes,
            "fields": fields,
            "pipeline": pipeline,
            "search": search,
            "note": note,
        }
        body.update({k: v for k, v in optional.items() if v is not None})
        return await self._t.patch(f"/collections/{collection_id}", body)

    async def delete(self, collection_id: str) -> Any:
        """
        Delete a collection (404 when unknown).

        Args:
            collection_id (str): The collection's UUID.
        """
        return await self._t.delete(f"/collections/{collection_id}")
