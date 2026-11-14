# ====== Code Summary ======
# The asynchronous collections (CRUD over a collection's full contract) resource: the awaiting shell
# over the shared ``_CollectionsSpecs`` builders.

# ====== Standard Library Imports ======
# `list`/`dict` annotations must stay lazy: a `list(...)` method in this class shadows the builtin in
# the class namespace, so eager annotation evaluation would break `list[str]` param hints (PEP 563).
# For the same reason, param hints below use `typing.List` (unshadowed) rather than the bare builtin,
# which the class-scoped `list` method otherwise resolves to under static analysis.
from __future__ import annotations

import builtins
from pathlib import Path
from typing import Any, Literal

# ====== Local Project Imports ======
from ...models.collections import (
    BulkReingestAccepted,
    BulkReingestRequest,
    CollectionContractSchemaResponse,
    CollectionDescription,
    CollectionListItem,
    CollectionModel,
    CreateCollectionRequest,
    UpdateCollectionRequest,
    UpdateCollectionResponse,
)
from ...models.corpus import DocumentFilter
from ...models.estimate import CollectionEstimateRequest, CostEstimate
from ...models.health import CollectionHealthResponse
from ...models.index_rebuild import RebuildIndexAccepted
from ...models.preview import PreviewJobAccepted, PreviewJobResult, PreviewResponse
from ...models.storage import CollectionStorageResponse
from ...models.trace import TracePurgeResult
from .._base import AsyncResource
from .specs import _CollectionsSpecs


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

    async def update(
        self, collection_id: str, request: UpdateCollectionRequest
    ) -> UpdateCollectionResponse:
        """
        Patch identity/limits, the metadata schema and/or the config blobs.

        Args:
            collection_id (str): The collection to patch.
            request (UpdateCollectionRequest): The partial patch body.

        Returns:
            UpdateCollectionResponse: The updated contract (unchanged under ``dry_run``) plus its
                ``schema_diff``.
        """
        return await self._transport.request(
            self._update_spec(collection_id, request), UpdateCollectionResponse
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

    async def describe(self, collection_id: str) -> CollectionDescription:
        """
        Fetch the agent guide: fields (meaning, type, example values), valid search targets, the
        filter grammar and ready-to-send example requests. Never includes pipeline/search config.

        Args:
            collection_id (str): The collection's UUID.

        Returns:
            CollectionDescription: The lean guide to query this collection.
        """
        return await self._transport.request(
            self._describe_spec(collection_id), CollectionDescription
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

    async def purge_trace_payloads(self, collection_id: str) -> TracePurgeResult:
        """
        Reclaim a collection's stored full execution-trace payloads (the heavy per-node raw bytes).

        Idempotent: a collection that stored no full-trace payloads returns zeros, not an error
        (404 only when the collection itself is unknown). Best-effort server-side, so the call always
        succeeds and reports the counts.

        Args:
            collection_id (str): The collection whose trace payloads are purged.

        Returns:
            TracePurgeResult: Jobs considered + object-store objects deleted.
        """
        return await self._transport.request(
            self._purge_trace_payloads_spec(collection_id), TracePurgeResult
        )

    async def rebuild_index(self, collection_id: str) -> RebuildIndexAccepted:
        """
        Rebuild the collection's vector index from its current schema — no content re-embed.

        Declares the named vectors of fields made semantic/lexical after first ingest, then refills
        the metadata vectors from Postgres (the dense metadata values go through the embed provider).
        Uploads and reingests are refused (409 ``rebuild_index_active``) while it runs. Poll
        ``jobs.get(job_id)`` — the job's ``document_id`` is None.

        Args:
            collection_id (str): The collection whose index is rebuilt.

        Returns:
            RebuildIndexAccepted: The queued job (202). 409 ``rebuild_index_active`` /
                ``collection_busy`` surface as a ConflictError.
        """
        return await self._transport.request(
            self._rebuild_index_spec(collection_id), RebuildIndexAccepted
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
