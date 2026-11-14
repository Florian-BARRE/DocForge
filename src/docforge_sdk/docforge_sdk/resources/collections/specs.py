# ====== Code Summary ======
# The pure ``RequestSpec`` builders of the collections (CRUD over a collection's full contract)
# resource — the single source of its URL/param/body logic, shared verbatim by the async and sync
# resources so their bodies differ ONLY by ``await``.

# ====== Standard Library Imports ======
# `list`/`dict` annotations must stay lazy: a `list(...)` method in this class shadows the builtin in
# the class namespace, so eager annotation evaluation would break `list[str]` param hints (PEP 563).
# For the same reason, param hints below use `typing.List` (unshadowed) rather than the bare builtin,
# which the class-scoped `list` method otherwise resolves to under static analysis.
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# ====== Local Project Imports ======
from ..._requestspec import RequestSpec
from ...models.collections import (
    BulkReingestRequest,
    CreateCollectionRequest,
    UpdateCollectionRequest,
)
from ...models.estimate import CollectionEstimateRequest
from .._base import _ResourceMixin


class _CollectionsSpecs(_ResourceMixin):
    """Pure ``RequestSpec`` builders for the collections endpoints — the single source of URL/body logic."""

    _COLLECTIONS_PATH = "/collections"

    def _list_spec(self) -> RequestSpec:
        """
        Build the spec for listing collections.

        Returns:
            RequestSpec: A GET on the collections collection.
        """
        return RequestSpec("GET", self._COLLECTIONS_PATH)

    def _get_spec(self, collection_id: str) -> RequestSpec:
        """
        Build the spec for fetching one collection.

        Args:
            collection_id (str): The collection's UUID.

        Returns:
            RequestSpec: A GET on the collection resource.
        """
        return RequestSpec("GET", f"{self._COLLECTIONS_PATH}/{collection_id}")

    def _create_spec(self, request: CreateCollectionRequest) -> RequestSpec:
        """
        Build the spec for creating a collection.

        Args:
            request (CreateCollectionRequest): The create body (contract + schema + pipeline).

        Returns:
            RequestSpec: A POST to the collections collection carrying the full body.
        """
        return RequestSpec("POST", self._COLLECTIONS_PATH, json=request.model_dump(mode="json"))

    def _update_spec(self, collection_id: str, request: UpdateCollectionRequest) -> RequestSpec:
        """
        Build the spec for patching a collection, sending only the caller-set fields.

        Args:
            collection_id (str): The collection to patch.
            request (UpdateCollectionRequest): The patch body (partial by design).

        Returns:
            RequestSpec: A PATCH on the collection resource with a minimal body.
        """
        return RequestSpec(
            "PATCH",
            f"{self._COLLECTIONS_PATH}/{collection_id}",
            json=request.model_dump(mode="json", exclude_unset=True),
        )

    def _delete_spec(self, collection_id: str) -> RequestSpec:
        """
        Build the spec for deleting a collection.

        Args:
            collection_id (str): The collection to delete.

        Returns:
            RequestSpec: A DELETE on the collection resource.
        """
        return RequestSpec("DELETE", f"{self._COLLECTIONS_PATH}/{collection_id}")

    def _health_spec(self, collection_id: str) -> RequestSpec:
        """
        Build the spec for probing a collection's on-demand operational health.

        Args:
            collection_id (str): The collection's UUID.

        Returns:
            RequestSpec: A GET on the collection's health sub-resource.
        """
        return RequestSpec("GET", f"{self._COLLECTIONS_PATH}/{collection_id}/health")

    def _describe_spec(self, collection_id: str) -> RequestSpec:
        """
        Build the spec for the lean agent-oriented collection guide.

        Args:
            collection_id (str): The collection's UUID.

        Returns:
            RequestSpec: A GET on the collection's describe sub-resource.
        """
        return RequestSpec("GET", f"{self._COLLECTIONS_PATH}/{collection_id}/describe")

    def _storage_spec(self, collection_id: str) -> RequestSpec:
        """
        Build the spec for measuring a collection's material storage footprint.

        Args:
            collection_id (str): The collection's UUID.

        Returns:
            RequestSpec: A GET on the collection's storage sub-resource.
        """
        return RequestSpec("GET", f"{self._COLLECTIONS_PATH}/{collection_id}/storage")

    def _purge_trace_payloads_spec(self, collection_id: str) -> RequestSpec:
        """
        Build the spec for reclaiming a collection's stored full execution-trace payloads.

        Args:
            collection_id (str): The collection whose trace payloads are purged.

        Returns:
            RequestSpec: A POST on the collection's ``/trace-payloads/purge`` sub-resource.
        """
        return RequestSpec("POST", f"{self._COLLECTIONS_PATH}/{collection_id}/trace-payloads/purge")

    def _rebuild_index_spec(self, collection_id: str) -> RequestSpec:
        """
        Build the spec for rebuilding a collection's vector index from its current schema.

        Args:
            collection_id (str): The collection whose index is rebuilt.

        Returns:
            RequestSpec: A POST on the collection's ``/rebuild-index`` route (no body).
        """
        return RequestSpec("POST", f"{self._COLLECTIONS_PATH}/{collection_id}/rebuild-index")

    def _reingest_spec(self, collection_id: str, request: BulkReingestRequest) -> RequestSpec:
        """
        Build the spec for re-running the full pipeline over a collection's corpus.

        Args:
            collection_id (str): The collection to re-ingest.
            request (BulkReingestRequest): Whole collection (default) or an explicit subset.

        Returns:
            RequestSpec: A POST on the collection's ``/reingest`` route with the subset body.
        """
        return RequestSpec(
            "POST",
            f"{self._COLLECTIONS_PATH}/{collection_id}/reingest",
            json=request.model_dump(mode="json"),
        )

    def _estimate_spec(self, collection_id: str, request: CollectionEstimateRequest) -> RequestSpec:
        """
        Build the spec for projecting a collection's ingestion cost/volume before spending.

        Args:
            collection_id (str): The collection to estimate over.
            request (CollectionEstimateRequest): The scope, or an explicit document-id/filter subset.

        Returns:
            RequestSpec: A POST on the collection's ``/estimate`` route with the selector body.
        """
        return RequestSpec(
            "POST",
            f"{self._COLLECTIONS_PATH}/{collection_id}/estimate",
            json=request.model_dump(mode="json", exclude_none=True),
        )

    def _contract_schema_spec(self) -> RequestSpec:
        """A GET of the collection identity/limits contract's JSON Schema (discovery)."""
        return RequestSpec("GET", f"{self._COLLECTIONS_PATH}/contract-schema")

    def _preview_job_spec(self, collection_id: str, preview_id: str) -> RequestSpec:
        """A GET poll of an asynchronous worker-side dry-run preview job by its id."""
        return RequestSpec(
            "GET",
            f"{self._COLLECTIONS_PATH}/{collection_id}/pipeline/preview/jobs/{preview_id}",
        )

    @staticmethod
    def _preview_parts(
        file: str | Path | bytes | None,
        document_id: str | None,
        blob: dict[str, Any] | None,
        metadata: dict[str, Any] | None,
        max_chunks: int | None,
        filename: str | None,
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        """
        Build the multipart ``files`` + form ``data`` of a dry-run preview request.

        Exactly one SOURCE is expected (a file XOR a document_id); the candidate blob, declared
        metadata and chunk ceiling are optional form fields. Returns ``files=None`` for the
        document-id path so the request is sent as a plain form body (no empty file part).

        Args:
            file (str | Path | bytes | None): A local path or raw bytes to dry-run, or None.
            document_id (str | None): An existing document to dry-run instead of a file, or None.
            blob (dict | None): A candidate pipeline blob to preview instead of the stored one.
            metadata (dict | None): Declared metadata for an uploaded source.
            max_chunks (int | None): How many preview chunks to return (capped server-side).
            filename (str | None): Override name for a bytes upload; defaults to the path name.

        Returns:
            tuple[dict | None, dict]: The httpx ``files`` mapping (None without a file) and form data.
        """
        # 1. Assemble the optional form fields shared by both source kinds.
        data: dict[str, str] = {}
        if document_id is not None:
            data["document_id"] = document_id
        if blob is not None:
            data["blob"] = json.dumps(blob)
        if metadata is not None:
            data["metadata"] = json.dumps(metadata)
        if max_chunks is not None:
            data["max_chunks"] = str(max_chunks)

        # 2. No uploaded file → a plain form body (document-id path).
        if file is None:
            return None, data

        # 3. Resolve the file part from a path or in-memory bytes.
        if isinstance(file, bytes):
            content, resolved_name = file, (filename or "upload")
        else:
            path = Path(file)
            content, resolved_name = path.read_bytes(), (filename or path.name)
        return {"file": (resolved_name, content)}, data
