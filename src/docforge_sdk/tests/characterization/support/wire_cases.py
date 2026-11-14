# ====== Code Summary ======
# The fixed call table of the wire characterization: one entry per public resource method (a few have
# a minimal and a full variant), each with the exact arguments the recording is made with. A case id is
# ``<resource attribute>.<method>`` or ``<resource attribute>.<method>#<variant>``. The table is the
# only place that knows the arguments; the recorder (wire_recorder.py) and the tests never guess them.

# ====== Standard Library Imports ======
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# ====== Internal Project Imports ======
from docforge_sdk.models._shared import KeyPermissions
from docforge_sdk.models.collections import (
    BulkReingestRequest,
    CreateCollectionRequest,
    UpdateCollectionRequest,
)
from docforge_sdk.models.corpus import (
    DocumentFilter,
    DocumentQueryRequest,
    DocumentSelector,
    DocumentSort,
    Pagination,
    TextFilter,
)
from docforge_sdk.models.explorer import BulkChunkEnabledPatch
from docforge_sdk.models.schema_ops import RemoveFieldOp
from docforge_sdk.models.search import ChunkBrowseRequest, SearchRequest
from docforge_sdk.models.snippets import CollectionSnippet

COLLECTION = "11111111-1111-1111-1111-111111111111"
DOCUMENT = "22222222-2222-2222-2222-222222222222"
CHUNK = "33333333-3333-3333-3333-333333333333"
JOB = "44444444-4444-4444-4444-444444444444"
KEY = "55555555-5555-5555-5555-555555555555"
TRANSFER = "66666666-6666-6666-6666-666666666666"
PREVIEW = "77777777-7777-7777-7777-777777777777"
EVENT = "88888888-8888-8888-8888-888888888888"
_MOMENT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
_BLOB = {"nodes": [{"id": "n1", "kind": "parse"}], "edges": []}
_ACTION = {"op": "set_provider", "node_id": "n1"}


@dataclass(frozen=True)
class WireCase:
    """
    One recorded SDK call.

    Attributes:
        case_id (str): ``<resource>.<method>`` or ``<resource>.<method>#<variant>``.
        make_kwargs (Callable[[], dict[str, Any]]): Builds fresh arguments (models are never shared
            between the async and the sync call).
        drain (bool): Consume the result as a byte stream (a streaming download).
    """

    case_id: str
    make_kwargs: Callable[[], dict[str, Any]] = field(default=dict)
    drain: bool = False

    @property
    def resource(self) -> str:
        """The client attribute the method hangs on (``jobs`` for ``jobs.list#full``)."""
        return self.case_id.split(".")[0]

    @property
    def method(self) -> str:
        """The method name (``list`` for ``jobs.list#full``)."""
        return self.case_id.split(".")[1].split("#")[0]


def _selector() -> DocumentSelector:
    """A selector mixing explicit ids, a filter and an exclusion."""
    return DocumentSelector(
        document_ids=[DOCUMENT],
        filter=DocumentFilter(filename=TextFilter(contains="report")),
        exclude_ids=[CHUNK],
    )


def _case(case_id: str, drain: bool = False, **kwargs: Any) -> WireCase:
    """Shorthand for a case whose arguments are plain, immutable values."""
    return WireCase(case_id, lambda: dict(kwargs), drain)


def _built(case_id: str, build: Callable[[], dict[str, Any]]) -> WireCase:
    """Shorthand for a case whose arguments contain request models, rebuilt per call."""
    return WireCase(case_id, build)


CASES: list[WireCase] = [
    # ------------------- audit / auth / health / capabilities ------------------- #
    _case("audit.list#min"),
    _case(
        "audit.list#full",
        limit=10,
        cursor="cur",
        actor_user_id="u1",
        actor_key_id="k1",
        target_type="collection",
        target_id=COLLECTION,
        correlation_id="corr",
        created_from=_MOMENT,
        created_to=_MOMENT,
    ),
    _case("auth.list_keys"),
    _case("auth.whoami"),
    _case("auth.create_key#min", name="ci"),
    _built(
        "auth.create_key#full",
        lambda: {
            "name": "ci",
            "permissions": KeyPermissions(collections=[COLLECTION]),
            "expires_at": _MOMENT,
        },
    ),
    _case("auth.revoke_key", key_id=KEY),
    _case("auth.rotate_key#min", key_id=KEY),
    _case(
        "auth.rotate_key#explicit_none", key_id=KEY, name=None, permissions=None, expires_at=None
    ),
    _built(
        "auth.rotate_key#full",
        lambda: {
            "key_id": KEY,
            "name": "renamed",
            "permissions": KeyPermissions(collections=[COLLECTION]),
            "expires_at": _MOMENT,
        },
    ),
    _case("health.ping"),
    _case("capabilities.capabilities"),
    # ------------------- blobs ------------------- #
    _case("blobs.get", content_hash="abc123"),
    # ------------------- collection aliases ------------------- #
    _case("collection_aliases.list"),
    _case("collection_aliases.set", name="prod", collection_id=COLLECTION),
    _case("collection_aliases.delete", name="prod"),
    # ------------------- collections ------------------- #
    _case("collections.list"),
    _case("collections.contract_schema"),
    _case("collections.get", collection_id=COLLECTION),
    _built(
        "collections.create",
        lambda: {
            "request": CreateCollectionRequest(
                name="docs", supported_formats=["pdf"], max_file_size_bytes=1000
            )
        },
    ),
    _built(
        "collections.update#min",
        lambda: {
            "collection_id": COLLECTION,
            "request": UpdateCollectionRequest(name="renamed"),
        },
    ),
    _built(
        "collections.update#full",
        lambda: {
            "collection_id": COLLECTION,
            "request": UpdateCollectionRequest(
                name="renamed",
                tags=["a"],
                title_field=None,
                field_ops=[RemoveFieldOp(op="remove", field_name="old")],
                dry_run=True,
                note="why",
            ),
        },
    ),
    _case("collections.delete", collection_id=COLLECTION),
    _case("collections.describe", collection_id=COLLECTION),
    _case("collections.health", collection_id=COLLECTION),
    _case("collections.storage", collection_id=COLLECTION),
    _case("collections.purge_trace_payloads", collection_id=COLLECTION),
    _case("collections.rebuild_index", collection_id=COLLECTION),
    _case("collections.reingest#min", collection_id=COLLECTION),
    _built(
        "collections.reingest#full",
        lambda: {
            "collection_id": COLLECTION,
            "request": BulkReingestRequest(
                document_ids=[DOCUMENT], force=True, replay_from="chunk", confirm_estimate=True
            ),
        },
    ),
    _case("collections.estimate#min", collection_id=COLLECTION),
    _case(
        "collections.estimate#document_ids",
        collection_id=COLLECTION,
        scope="all",
        document_ids=[DOCUMENT],
    ),
    _built(
        "collections.estimate#filter",
        lambda: {
            "collection_id": COLLECTION,
            "filter": DocumentFilter(filename=TextFilter(contains="report")),
        },
    ),
    _case("collections.preview_pipeline#document", collection_id=COLLECTION, document_id=DOCUMENT),
    _case(
        "collections.preview_pipeline#file",
        collection_id=COLLECTION,
        file=b"%PDF-1.4 bytes",
        filename="a.pdf",
        metadata={"topic": "x"},
        max_chunks=3,
    ),
    _case("collections.preview_pipeline#blob", collection_id=COLLECTION, blob=_BLOB),
    _case(
        "collections.submit_preview_job#document", collection_id=COLLECTION, document_id=DOCUMENT
    ),
    _case(
        "collections.submit_preview_job#file",
        collection_id=COLLECTION,
        file=b"%PDF-1.4 bytes",
        filename="a.pdf",
        metadata={"topic": "x"},
        max_chunks=3,
    ),
    _case("collections.get_preview_job", collection_id=COLLECTION, preview_id=PREVIEW),
    # ------------------- config versions / snippets ------------------- #
    _case("config_versions.list#min", collection_id=COLLECTION),
    _case("config_versions.list#full", collection_id=COLLECTION, limit=5, offset=10),
    _case("config_versions.get", collection_id=COLLECTION, version=3),
    _case("config_versions.diff", collection_id=COLLECTION, from_version=1, to_version=3),
    _case("config_versions.restore", collection_id=COLLECTION, version=2),
    _case("snippets.export", collection_id=COLLECTION, kind="search"),
    _built(
        "snippets.apply",
        lambda: {
            "collection_id": COLLECTION,
            "kind": "pipeline",
            "snippet": CollectionSnippet(
                kind="pipeline", format_version=1, docforge_version="0.14.3", body={"nodes": []}
            ),
        },
    ),
    # ------------------- corpus ------------------- #
    _case("corpus.query#min", collection_id=COLLECTION),
    _built(
        "corpus.query#full",
        lambda: {
            "collection_id": COLLECTION,
            "request": DocumentQueryRequest(
                filter=DocumentFilter(filename=TextFilter(contains="report")),
                sort=DocumentSort(field="filename", direction="asc"),
                pagination=Pagination(limit=10, offset=20),
            ),
        },
    ),
    _built("corpus.bulk_delete", lambda: {"collection_id": COLLECTION, "selector": _selector()}),
    _built(
        "corpus.bulk_set_enabled",
        lambda: {"collection_id": COLLECTION, "selector": _selector(), "enabled": False},
    ),
    _built(
        "corpus.bulk_reingest#min", lambda: {"collection_id": COLLECTION, "selector": _selector()}
    ),
    _built(
        "corpus.bulk_reingest#full",
        lambda: {
            "collection_id": COLLECTION,
            "selector": _selector(),
            "force": True,
            "replay_from": "embed",
            "confirm_estimate": True,
        },
    ),
    # ------------------- documents ------------------- #
    _case("documents.upload#min", collection_id=COLLECTION, file=b"hello"),
    _case(
        "documents.upload#full",
        collection_id=COLLECTION,
        file=b"hello",
        metadata={"topic": "x", "n": 2},
        filename="note.txt",
    ),
    _case("documents.set_enabled", document_id=DOCUMENT, enabled=False),
    _case("documents.update_metadata", document_id=DOCUMENT, values={"topic": "x", "n": None}),
    _case("documents.reingest#min", document_id=DOCUMENT),
    _case("documents.reingest#full", document_id=DOCUMENT, force=True, replay_from="enrich"),
    _case("documents.purge_trace_payloads", document_id=DOCUMENT),
    _case("documents.get_markdown#min", document_id=DOCUMENT),
    _case("documents.get_markdown#full", document_id=DOCUMENT, download=True, pages="1-3"),
    _case("documents.get_html#min", document_id=DOCUMENT),
    _case("documents.get_html#full", document_id=DOCUMENT, download=True, pages="2"),
    # ------------------- explorer ------------------- #
    _case("explorer.list_documents#min", collection_id=COLLECTION),
    _case("explorer.list_documents#full", collection_id=COLLECTION, limit=5, offset=10),
    _case("explorer.get_document", document_id=DOCUMENT),
    _case("explorer.get_pages", document_id=DOCUMENT),
    _case("explorer.get_ir", document_id=DOCUMENT),
    _case("explorer.get_provenance", document_id=DOCUMENT),
    _case("explorer.get_outline", document_id=DOCUMENT),
    _case("explorer.get_chunks#min", document_id=DOCUMENT),
    _case(
        "explorer.get_chunks#full", document_id=DOCUMENT, limit=5, offset=10, include_geometry=True
    ),
    _case("explorer.get_chunks_page#min", document_id=DOCUMENT),
    _case(
        "explorer.get_chunks_page#full",
        document_id=DOCUMENT,
        limit=5,
        offset=10,
        include_geometry=True,
    ),
    _case("explorer.get_chunk_context#min", chunk_id=CHUNK),
    _case("explorer.get_chunk_context#full", chunk_id=CHUNK, before=2, after=3),
    _case("explorer.set_chunk_enabled", chunk_id=CHUNK, enabled=False),
    _built(
        "explorer.set_chunks_enabled",
        lambda: {"patch": BulkChunkEnabledPatch(chunk_ids=[CHUNK], enabled=True)},
    ),
    _case("explorer.delete_document", document_id=DOCUMENT),
    # ------------------- jobs ------------------- #
    _case("jobs.list#min"),
    _case(
        "jobs.list#full",
        collection_id=COLLECTION,
        status=["failed", "done"],
        order="asc",
        limit=5,
        offset=10,
        stage="embed",
        error_type="timeout",
        search="q",
        created_after="2026-01-01T00:00:00Z",
        created_before="2026-02-01T00:00:00Z",
        sort="status",
    ),
    _case("jobs.get", job_id=JOB),
    _case("jobs.get_events", job_id=JOB),
    _case("jobs.get_event_payload#min", job_id=JOB, event_id=EVENT),
    _case("jobs.get_event_payload#input", job_id=JOB, event_id=EVENT, slot="input"),
    _case("jobs.live_workers"),
    _case("jobs.cancel#min", job_id=JOB),
    _case("jobs.cancel#force", job_id=JOB, force=True),
    _case("jobs.cost", collection_id=COLLECTION),
    _case("jobs.queue#min"),
    _case("jobs.queue#full", collection_id=COLLECTION),
    _case("jobs.stage_durations", collection_id=COLLECTION),
    _case("jobs.failure_breakdown#min"),
    _case("jobs.failure_breakdown#full", collection_id=COLLECTION, window_hours=24),
    _case("jobs.new_failures#min", since="2026-01-01T00:00:00Z"),
    _case(
        "jobs.new_failures#full",
        since="2026-01-01T00:00:00Z",
        collection_id=COLLECTION,
        include_ids=True,
        limit=7,
    ),
    _case("jobs.timeseries#min"),
    _case("jobs.timeseries#full", collection_id=COLLECTION, window_hours=48),
    # ------------------- pipelines ------------------- #
    _case("pipelines.list_surfaces"),
    _case("pipelines.get_design#min", key="ingest"),
    _case("pipelines.get_design#full", key="ingest", full=True),
    _case("pipelines.inspect", key="ingest", blob=_BLOB),
    _case(
        "pipelines.edit", key="ingest", blob=_BLOB, operations=[{"op": "remove", "node_id": "n1"}]
    ),
    _case("pipelines.view_stages", key="ingest", blob=_BLOB),
    _case("pipelines.apply_stage", key="ingest", blob=_BLOB, action=_ACTION),
    _case("pipelines.apply_collection_stage#min", collection_id=COLLECTION, action=_ACTION),
    _case(
        "pipelines.apply_collection_stage#note",
        collection_id=COLLECTION,
        action=_ACTION,
        note="why",
    ),
    # ------------------- search ------------------- #
    _built(
        "search.search#min",
        lambda: {"collection_id": COLLECTION, "request": SearchRequest(query="hello")},
    ),
    _built(
        "search.search#full",
        lambda: {
            "collection_id": COLLECTION,
            "request": SearchRequest(
                query="hello",
                limit=5,
                filters={"topic": {"not": "x"}},
                return_fields=["text"],
                group_by="document",
                max_per_document=2,
                min_score=0.3,
                rerank=False,
                fusion="dbsf",
                debug=True,
            ),
        },
    ),
    _built(
        "search.browse#min",
        lambda: {"collection_id": COLLECTION, "request": ChunkBrowseRequest()},
    ),
    _built(
        "search.browse#full",
        lambda: {
            "collection_id": COLLECTION,
            "request": ChunkBrowseRequest(
                filters={"topic": "x"}, limit=5, cursor="abc", return_fields=["text"]
            ),
        },
    ),
    _case("search.get_search_health"),
    # ------------------- transfers ------------------- #
    _case("transfers.export_collection", collection_id=COLLECTION),
    _case("transfers.get_transfer", transfer_id=TRANSFER),
    _case("transfers.import_collection#min", file=b"bundle-bytes"),
    _case("transfers.import_collection#named", file=b"bundle-bytes", target_name="restored"),
    _case("transfers.download_export", drain=True, transfer_id=TRANSFER),
]

__all__ = ["CASES", "WireCase"]
