# ====== Code Summary ======
# The collections resource (CRUD over a collection's full contract). All URL/body logic lives once in
# the pure _CollectionsSpecs mixin, so AsyncCollections and SyncCollections have identical public
# surfaces whose bodies differ ONLY by ``await``.

# ====== Standard Library Imports ======
# `list`/`dict` annotations must stay lazy: a `list(...)` method in this class shadows the builtin in
# the class namespace, so eager annotation evaluation would break `list[str]` param hints (PEP 563).
# For the same reason, param hints below use `typing.List` (unshadowed) rather than the bare builtin,
# which the class-scoped `list` method otherwise resolves to under static analysis.
from __future__ import annotations

import builtins
import json
from pathlib import Path
from typing import Any, Literal

# ====== Local Project Imports ======
from .._requestspec import RequestSpec
from ..models.collections import (
    BulkReingestAccepted,
    BulkReingestRequest,
    CollectionContractSchemaResponse,
    CollectionListItem,
    CollectionModel,
    CreateCollectionRequest,
    UpdateCollectionRequest,
)
from ..models.corpus import DocumentFilter
from ..models.estimate import CollectionEstimateRequest, CostEstimate
from ..models.health import CollectionHealthResponse
from ..models.preview import PreviewJobAccepted, PreviewJobResult, PreviewResponse
from ..models.storage import CollectionStorageResponse
from ._base import AsyncResource, SyncResource, _ResourceMixin


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

    def _storage_spec(self, collection_id: str) -> RequestSpec:
        """
        Build the spec for measuring a collection's material storage footprint.

        Args:
            collection_id (str): The collection's UUID.

        Returns:
            RequestSpec: A GET on the collection's storage sub-resource.
        """
        return RequestSpec("GET", f"{self._COLLECTIONS_PATH}/{collection_id}/storage")

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


class AsyncCollections(AsyncResource, _CollectionsSpecs):
    """Asynchronous collection management (list / get / create / update / delete)."""

    async def list(self) -> list[CollectionListItem]:
        """
        List every collection with its full schema and server-computed health summary.

        Returns:
            list[CollectionListItem]: All contracts (schema included), each with its health summary.
        """
        return await self._transport.request(self._list_spec(), list[CollectionListItem])

    async def get(self, collection_id: str) -> CollectionModel:
        """
        Fetch one collection's full contract.

        Args:
            collection_id (str): The collection's UUID.

        Returns:
            CollectionModel: Identity, limits, schema and config blobs.
        """
        return await self._transport.request(self._get_spec(collection_id), CollectionModel)

    async def create(self, request: CreateCollectionRequest) -> CollectionModel:
        """
        Create a collection from its contract, schema and (optional) pipeline.

        Args:
            request (CreateCollectionRequest): The create body.

        Returns:
            CollectionModel: The created contract.
        """
        return await self._transport.request(self._create_spec(request), CollectionModel)

    async def update(self, collection_id: str, request: UpdateCollectionRequest) -> CollectionModel:
        """
        Patch identity/limits, the metadata schema and/or the config blobs.

        Args:
            collection_id (str): The collection to patch.
            request (UpdateCollectionRequest): The partial patch body.

        Returns:
            CollectionModel: The updated contract.
        """
        return await self._transport.request(
            self._update_spec(collection_id, request), CollectionModel
        )

    async def delete(self, collection_id: str) -> None:
        """
        Delete a collection.

        Args:
            collection_id (str): The collection to delete.
        """
        return await self._transport.request(self._delete_spec(collection_id), type(None))

    async def health(self, collection_id: str) -> CollectionHealthResponse:
        """
        Probe a collection's operational health on demand (no job enqueued, no spend).

        Args:
            collection_id (str): The collection's UUID.

        Returns:
            CollectionHealthResponse: Per-provider reachability, index stats and the rolled-up verdict.
        """
        return await self._transport.request(
            self._health_spec(collection_id), CollectionHealthResponse
        )

    async def storage(self, collection_id: str) -> CollectionStorageResponse:
        """
        Measure a collection's material footprint per store (S3 exact, Postgres/Qdrant estimated).

        Args:
            collection_id (str): The collection's UUID.

        Returns:
            CollectionStorageResponse: Per-store totals + the per-document breakdown, heaviest first.
        """
        return await self._transport.request(
            self._storage_spec(collection_id), CollectionStorageResponse
        )

    async def reingest(
        self, collection_id: str, request: BulkReingestRequest | None = None
    ) -> BulkReingestAccepted:
        """
        Re-run the full pipeline over a collection's corpus — all documents, or an explicit subset.

        A match above the server's per-call fan-out ceiling enqueues only the first N and reports
        ``capped=true`` with the full ``matched`` count. Poll each returned job handle for progress.

        Args:
            collection_id (str): The collection to re-ingest.
            request (BulkReingestRequest | None): The subset to re-run; omit for the whole collection.
                Set ``request.force`` to bypass the stage cache and recompute every stage.

        Returns:
            BulkReingestAccepted: matched / enqueued / capped + one job handle per enqueued run.
        """
        return await self._transport.request(
            self._reingest_spec(collection_id, request or BulkReingestRequest()),
            BulkReingestAccepted,
        )

    async def estimate(
        self,
        collection_id: str,
        scope: Literal["pending", "all"] = "pending",
        document_ids: builtins.list[str] | None = None,
        filter: DocumentFilter | None = None,
    ) -> CostEstimate:
        """
        Project a collection's ingestion cost and volume before spending a cent.

        Args:
            collection_id (str): The collection to estimate over.
            scope (str): Whole-collection selector used when neither subset below is given —
                ``pending`` (not-yet-ingested, the default) or ``all`` (every document).
            document_ids (list[str] | None): Estimate over exactly these document ids (mutually
                exclusive with ``filter``; overrides ``scope`` when set).
            filter (DocumentFilter | None): Estimate over the documents matching this corpus filter
                (mutually exclusive with ``document_ids``; overrides ``scope`` when set).

        Returns:
            CostEstimate: The per-stage breakdown, projected volume, totals, assumptions and caveats.
        """
        request = CollectionEstimateRequest(scope=scope, document_ids=document_ids, filter=filter)
        return await self._transport.request(
            self._estimate_spec(collection_id, request), CostEstimate
        )

    async def preview_pipeline(
        self,
        collection_id: str,
        *,
        file: str | Path | bytes | None = None,
        document_id: str | None = None,
        blob: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        max_chunks: int | None = None,
        filename: str | None = None,
    ) -> PreviewResponse:
        """
        Dry-run the ingestion pipeline on ONE document and return a bounded preview — nothing persisted.

        Provide exactly one source: ``file`` (a local path or raw bytes) OR ``document_id`` (an
        already-ingested document). Optionally pass a candidate ``blob`` to preview instead of the
        collection's stored pipeline. The server runs the ingest graph inline and returns an IR
        summary, the first N chunks, the run's actual metered cost and the execution trace, writing
        no document / blob / vector.

        Args:
            collection_id (str): The collection whose contract + pipeline the run uses.
            file (str | Path | bytes | None): A local path or raw bytes to dry-run.
            document_id (str | None): An existing document to dry-run instead of a file.
            blob (dict | None): A candidate pipeline blob to preview instead of the stored one.
            metadata (dict | None): Declared metadata for an uploaded source (field → value).
            max_chunks (int | None): How many preview chunks to return (capped server-side).
            filename (str | None): Override name for a bytes upload; defaults to the path name.

        Returns:
            PreviewResponse: The bounded dry-run report (ok=false + trace when a node failed).
        """
        files, data = self._preview_parts(file, document_id, blob, metadata, max_chunks, filename)
        return await self._transport.upload(
            f"{self._COLLECTIONS_PATH}/{collection_id}/pipeline/preview",
            files,
            data,
            PreviewResponse,
        )

    async def submit_preview_job(
        self,
        collection_id: str,
        *,
        file: str | Path | bytes | None = None,
        document_id: str | None = None,
        blob: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        max_chunks: int | None = None,
        filename: str | None = None,
    ) -> PreviewJobAccepted:
        """
        Submit an ASYNCHRONOUS worker-side dry-run preview — returns a pollable id, persists nothing.

        Unlike ``preview_pipeline`` (inline, API-process), this enqueues a WORKER job that runs the
        full ingest graph with every dependency present (docling included), so it covers ALL pipelines.
        Poll the returned id with ``get_preview_job`` until its status is terminal.

        Args:
            collection_id (str): The collection whose contract + pipeline the run uses.
            file (str | Path | bytes | None): A local path or raw bytes to dry-run.
            document_id (str | None): An existing document to dry-run instead of a file.
            blob (dict | None): A candidate pipeline blob to preview instead of the stored one.
            metadata (dict | None): Declared metadata for an uploaded source (field → value).
            max_chunks (int | None): How many preview chunks to return (capped server-side).
            filename (str | None): Override name for a bytes upload; defaults to the path name.

        Returns:
            PreviewJobAccepted: The preview id + initial status (poll it with ``get_preview_job``).
        """
        files, data = self._preview_parts(file, document_id, blob, metadata, max_chunks, filename)
        return await self._transport.upload(
            f"{self._COLLECTIONS_PATH}/{collection_id}/pipeline/preview/jobs",
            files,
            data,
            PreviewJobAccepted,
        )

    async def get_preview_job(self, collection_id: str, preview_id: str) -> PreviewJobResult:
        """
        Poll an asynchronous dry-run preview by its id — the report appears once status is 'done'.

        A failed NODE is DATA: status 'done' with ``result.ok`` = false. 'failed' is reserved for the
        worker job itself crashing/timing out. An unknown/expired id is a 404.

        Args:
            collection_id (str): The collection the preview belongs to.
            preview_id (str): The id returned by ``submit_preview_job``.

        Returns:
            PreviewJobResult: status + (the bounded report when done).
        """
        return await self._transport.request(
            self._preview_job_spec(collection_id, preview_id), PreviewJobResult
        )

    async def contract_schema(self) -> CollectionContractSchemaResponse:
        """The JSON Schema of the collection identity/limits contract (drives a discovery form)."""
        return await self._transport.request(
            self._contract_schema_spec(), CollectionContractSchemaResponse
        )


class SyncCollections(SyncResource, _CollectionsSpecs):
    """Synchronous collection management (list / get / create / update / delete)."""

    def list(self) -> list[CollectionListItem]:
        """
        List every collection with its full schema and server-computed health summary.

        Returns:
            list[CollectionListItem]: All contracts (schema included), each with its health summary.
        """
        return self._transport.request(self._list_spec(), list[CollectionListItem])

    def get(self, collection_id: str) -> CollectionModel:
        """
        Fetch one collection's full contract.

        Args:
            collection_id (str): The collection's UUID.

        Returns:
            CollectionModel: Identity, limits, schema and config blobs.
        """
        return self._transport.request(self._get_spec(collection_id), CollectionModel)

    def create(self, request: CreateCollectionRequest) -> CollectionModel:
        """
        Create a collection from its contract, schema and (optional) pipeline.

        Args:
            request (CreateCollectionRequest): The create body.

        Returns:
            CollectionModel: The created contract.
        """
        return self._transport.request(self._create_spec(request), CollectionModel)

    def update(self, collection_id: str, request: UpdateCollectionRequest) -> CollectionModel:
        """
        Patch identity/limits, the metadata schema and/or the config blobs.

        Args:
            collection_id (str): The collection to patch.
            request (UpdateCollectionRequest): The partial patch body.

        Returns:
            CollectionModel: The updated contract.
        """
        return self._transport.request(self._update_spec(collection_id, request), CollectionModel)

    def delete(self, collection_id: str) -> None:
        """
        Delete a collection.

        Args:
            collection_id (str): The collection to delete.
        """
        return self._transport.request(self._delete_spec(collection_id), type(None))

    def health(self, collection_id: str) -> CollectionHealthResponse:
        """
        Probe a collection's operational health on demand (no job enqueued, no spend).

        Args:
            collection_id (str): The collection's UUID.

        Returns:
            CollectionHealthResponse: Per-provider reachability, index stats and the rolled-up verdict.
        """
        return self._transport.request(self._health_spec(collection_id), CollectionHealthResponse)

    def storage(self, collection_id: str) -> CollectionStorageResponse:
        """
        Measure a collection's material footprint per store (S3 exact, Postgres/Qdrant estimated).

        Args:
            collection_id (str): The collection's UUID.

        Returns:
            CollectionStorageResponse: Per-store totals + the per-document breakdown, heaviest first.
        """
        return self._transport.request(self._storage_spec(collection_id), CollectionStorageResponse)

    def reingest(
        self, collection_id: str, request: BulkReingestRequest | None = None
    ) -> BulkReingestAccepted:
        """
        Re-run the full pipeline over a collection's corpus — all documents, or an explicit subset.

        A match above the server's per-call fan-out ceiling enqueues only the first N and reports
        ``capped=true`` with the full ``matched`` count. Poll each returned job handle for progress.

        Args:
            collection_id (str): The collection to re-ingest.
            request (BulkReingestRequest | None): The subset to re-run; omit for the whole collection.
                Set ``request.force`` to bypass the stage cache and recompute every stage.

        Returns:
            BulkReingestAccepted: matched / enqueued / capped + one job handle per enqueued run.
        """
        return self._transport.request(
            self._reingest_spec(collection_id, request or BulkReingestRequest()),
            BulkReingestAccepted,
        )

    def estimate(
        self,
        collection_id: str,
        scope: Literal["pending", "all"] = "pending",
        document_ids: builtins.list[str] | None = None,
        filter: DocumentFilter | None = None,
    ) -> CostEstimate:
        """
        Project a collection's ingestion cost and volume before spending a cent.

        Args:
            collection_id (str): The collection to estimate over.
            scope (str): Whole-collection selector used when neither subset below is given —
                ``pending`` (not-yet-ingested, the default) or ``all`` (every document).
            document_ids (list[str] | None): Estimate over exactly these document ids (mutually
                exclusive with ``filter``; overrides ``scope`` when set).
            filter (DocumentFilter | None): Estimate over the documents matching this corpus filter
                (mutually exclusive with ``document_ids``; overrides ``scope`` when set).

        Returns:
            CostEstimate: The per-stage breakdown, projected volume, totals, assumptions and caveats.
        """
        request = CollectionEstimateRequest(scope=scope, document_ids=document_ids, filter=filter)
        return self._transport.request(self._estimate_spec(collection_id, request), CostEstimate)

    def preview_pipeline(
        self,
        collection_id: str,
        *,
        file: str | Path | bytes | None = None,
        document_id: str | None = None,
        blob: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        max_chunks: int | None = None,
        filename: str | None = None,
    ) -> PreviewResponse:
        """
        Dry-run the ingestion pipeline on ONE document and return a bounded preview — nothing persisted.

        Provide exactly one source: ``file`` (a local path or raw bytes) OR ``document_id`` (an
        already-ingested document). Optionally pass a candidate ``blob`` to preview instead of the
        collection's stored pipeline. The server runs the ingest graph inline and returns an IR
        summary, the first N chunks, the run's actual metered cost and the execution trace, writing
        no document / blob / vector.

        Args:
            collection_id (str): The collection whose contract + pipeline the run uses.
            file (str | Path | bytes | None): A local path or raw bytes to dry-run.
            document_id (str | None): An existing document to dry-run instead of a file.
            blob (dict | None): A candidate pipeline blob to preview instead of the stored one.
            metadata (dict | None): Declared metadata for an uploaded source (field → value).
            max_chunks (int | None): How many preview chunks to return (capped server-side).
            filename (str | None): Override name for a bytes upload; defaults to the path name.

        Returns:
            PreviewResponse: The bounded dry-run report (ok=false + trace when a node failed).
        """
        files, data = self._preview_parts(file, document_id, blob, metadata, max_chunks, filename)
        return self._transport.upload(
            f"{self._COLLECTIONS_PATH}/{collection_id}/pipeline/preview",
            files,
            data,
            PreviewResponse,
        )

    def submit_preview_job(
        self,
        collection_id: str,
        *,
        file: str | Path | bytes | None = None,
        document_id: str | None = None,
        blob: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        max_chunks: int | None = None,
        filename: str | None = None,
    ) -> PreviewJobAccepted:
        """
        Submit an ASYNCHRONOUS worker-side dry-run preview — returns a pollable id, persists nothing.

        Unlike ``preview_pipeline`` (inline, API-process), this enqueues a WORKER job that runs the
        full ingest graph with every dependency present (docling included), so it covers ALL pipelines.
        Poll the returned id with ``get_preview_job`` until its status is terminal.

        Args:
            collection_id (str): The collection whose contract + pipeline the run uses.
            file (str | Path | bytes | None): A local path or raw bytes to dry-run.
            document_id (str | None): An existing document to dry-run instead of a file.
            blob (dict | None): A candidate pipeline blob to preview instead of the stored one.
            metadata (dict | None): Declared metadata for an uploaded source (field → value).
            max_chunks (int | None): How many preview chunks to return (capped server-side).
            filename (str | None): Override name for a bytes upload; defaults to the path name.

        Returns:
            PreviewJobAccepted: The preview id + initial status (poll it with ``get_preview_job``).
        """
        files, data = self._preview_parts(file, document_id, blob, metadata, max_chunks, filename)
        return self._transport.upload(
            f"{self._COLLECTIONS_PATH}/{collection_id}/pipeline/preview/jobs",
            files,
            data,
            PreviewJobAccepted,
        )

    def get_preview_job(self, collection_id: str, preview_id: str) -> PreviewJobResult:
        """
        Poll an asynchronous dry-run preview by its id — the report appears once status is 'done'.

        A failed NODE is DATA: status 'done' with ``result.ok`` = false. 'failed' is reserved for the
        worker job itself crashing/timing out. An unknown/expired id is a 404.

        Args:
            collection_id (str): The collection the preview belongs to.
            preview_id (str): The id returned by ``submit_preview_job``.

        Returns:
            PreviewJobResult: status + (the bounded report when done).
        """
        return self._transport.request(
            self._preview_job_spec(collection_id, preview_id), PreviewJobResult
        )

    def contract_schema(self) -> CollectionContractSchemaResponse:
        """The JSON Schema of the collection identity/limits contract (drives a discovery form)."""
        return self._transport.request(
            self._contract_schema_spec(), CollectionContractSchemaResponse
        )


__all__ = ["AsyncCollections", "SyncCollections"]
