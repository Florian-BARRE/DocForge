# ====== Code Summary ======
# The input of the tool -> SDK call golden: for every MCP tool, one or more fixed argument sets
# (the tool's defaults, then each branch that shapes the request differently) and, for the few
# tools that make several SDK calls or branch on a response, the scripted return values that steer
# them. A new tool needs a case here (test_every_registered_tool_has_a_case), then a regenerated
# golden (`UPDATE_MCP_TOOL_CALLS_GOLDEN=1 uv run pytest tests/characterization`).

from __future__ import annotations

# ====== Standard Library Imports ======
import base64
from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

CID = "11111111-1111-1111-1111-111111111111"
OTHER_CID = "22222222-2222-2222-2222-222222222222"
DOC = "doc-1"
JOB = "job-1"
KEY = "key-1"

_PIPELINE_BLOB: dict[str, Any] = {"nodes": [{"id": "parse"}], "edges": []}
_FILTER: dict[str, Any] = {
    "status": ["done"],
    "filename": {"contains": "q3"},
    "metadata": [{"field": "year", "op": "gte", "value": 2023}],
}
_FIELD: dict[str, Any] = {
    "field_name": "topic",
    "field_type": "keyword_list",
    "filterable": True,
    "semantic": True,
    "origin": "user",
    "scope": "document",
    "description": "Subject of the document",
}
_PERMISSIONS: dict[str, Any] = {"profile": "agent_reader", "collections": [CID]}
_ISO = "2026-03-04T05:06:07+00:00"


class FakeModel(SimpleNamespace):
    """A scripted SDK response: attributes for the tool's own reads, `model_dump` for its output."""

    def __init__(self, dump: dict[str, Any] | None = None, **attributes: Any) -> None:
        super().__init__(**attributes)
        self._dump = dump if dump is not None else dict(attributes)

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """The scripted payload, whatever the dump options."""
        return dict(self._dump)


Returns = Callable[[], dict[str, list[Any]]]


@dataclass(frozen=True)
class ToolCase:
    """One tool invocation: the tool, its arguments and the scripted SDK returns (if any)."""

    case_id: str
    tool: str
    arguments: dict[str, Any]
    returns: Returns | None = None


def _case(
    tool: str, variant: str | None = None, returns: Returns | None = None, **arguments: Any
) -> ToolCase:
    case_id = tool if variant is None else f"{tool}:{variant}"
    return ToolCase(case_id, tool, arguments, returns)


def _alias(name: str, collection_id: str) -> FakeModel:
    return FakeModel(name=name, collection_id=collection_id, collection_name="Existing")


CASES: tuple[ToolCase, ...] = (
    # ---- health, capabilities
    _case("ping"),
    _case("get_capabilities"),
    # ---- auth
    _case("create_api_key", name="ci"),
    _case(
        "create_api_key",
        "scoped_and_expiring",
        name="ci",
        permissions=_PERMISSIONS,
        expires_at=_ISO,
    ),
    _case("list_api_keys"),
    _case("revoke_api_key", key_id=KEY),
    _case("rotate_api_key", key_id=KEY),
    _case(
        "rotate_api_key",
        "renamed_rescoped_expiring",
        key_id=KEY,
        name="renamed",
        permissions=_PERMISSIONS,
        expires_at=_ISO,
    ),
    _case("whoami"),
    # ---- collections
    _case("list_collections"),
    _case("get_collection", collection_id=CID),
    _case("describe_collection", collection_id=CID),
    _case(
        "create_collection",
        name="Contracts",
        supported_formats=["pdf", "docx"],
        max_file_size_bytes=1_000_000,
    ),
    _case(
        "create_collection",
        "every_option",
        name="Contracts",
        supported_formats=["pdf"],
        max_file_size_bytes=1_000_000,
        tags=["legal", "2026"],
        fields=[_FIELD],
        pipeline=_PIPELINE_BLOB,
        preset="ocr_scan",
        search_preset="hybrid_rerank",
        job_timeout_seconds=900.0,
        trace_verbosity="full",
        title_field="topic",
    ),
    _case("update_collection", "no_change", collection_id=CID),
    _case(
        "update_collection",
        "identity_and_blobs",
        collection_id=CID,
        name="Renamed",
        supported_formats=["pdf"],
        tags=["a"],
        max_file_size_bytes=2_000_000,
        pipeline=_PIPELINE_BLOB,
        search={"nodes": []},
        note="why",
    ),
    _case("update_collection", "set_title_field", collection_id=CID, title_field="topic"),
    _case(
        "update_collection",
        "clear_title_field_wins",
        collection_id=CID,
        title_field="topic",
        clear_title_field=True,
    ),
    _case(
        "update_collection",
        "add_field",
        collection_id=CID,
        field_ops=[{"op": "add", "field": _FIELD}],
    ),
    _case(
        "update_collection",
        "remove_field_unconfirmed_is_a_dry_run",
        collection_id=CID,
        field_ops=[{"op": "remove", "field_name": "topic"}],
    ),
    _case(
        "update_collection",
        "remove_field_confirmed_writes",
        collection_id=CID,
        field_ops=[{"op": "remove", "field_name": "topic"}],
        confirm=True,
    ),
    _case(
        "update_collection",
        "rename_field_unconfirmed_is_a_dry_run",
        collection_id=CID,
        field_ops=[{"op": "rename", "field_name": "topic", "new_name": "subject"}],
    ),
    _case("update_collection", "preview", collection_id=CID, name="Renamed", preview=True),
    _case("delete_collection", collection_id=CID),
    _case("collection_storage_footprint", collection_id=CID),
    _case("estimate_collection_cost", collection_id=CID),
    _case("estimate_collection_cost", "scope_all", collection_id=CID, scope="all"),
    _case(
        "estimate_collection_cost",
        "document_ids",
        collection_id=CID,
        document_ids=[DOC, "doc-2"],
    ),
    _case(
        "estimate_collection_cost",
        "filter",
        collection_id=CID,
        filter={"status": ["done"], "filename": {"contains": "q3"}},
    ),
    _case("preview_pipeline", collection_id=CID, document_id=DOC),
    _case(
        "preview_pipeline",
        "candidate_blob",
        collection_id=CID,
        document_id=DOC,
        blob=_PIPELINE_BLOB,
        max_chunks=5,
    ),
    _case("submit_preview_job", collection_id=CID, document_id=DOC),
    _case(
        "submit_preview_job",
        "candidate_blob",
        collection_id=CID,
        document_id=DOC,
        blob=_PIPELINE_BLOB,
        max_chunks=5,
    ),
    _case("get_preview_job", collection_id=CID, preview_id="preview-1"),
    _case("export_collection_snippet", collection_id=CID, kind="schema"),
    _case(
        "apply_collection_snippet",
        collection_id=CID,
        kind="pipeline",
        snippet={
            "kind": "pipeline",
            "format_version": 1,
            "docforge_version": "0.31.3",
            "body": _PIPELINE_BLOB,
        },
    ),
    _case("get_collection_contract_schema"),
    _case("collection_health", collection_id=CID),
    _case("reingest_collection", collection_id=CID),
    _case(
        "reingest_collection",
        "subset_forced_replayed_confirmed",
        collection_id=CID,
        document_ids=[DOC],
        force=True,
        replay_from="embed",
        confirm_estimate=True,
    ),
    _case("rebuild_collection_index", collection_id=CID),
    _case("purge_collection_trace_payloads", collection_id=CID),
    # ---- collection aliases
    _case("list_collection_aliases"),
    _case(
        "set_collection_alias",
        "new_alias_is_written",
        returns=lambda: {"collection_aliases.list": [[]]},
        name="chat",
        collection_id=CID,
    ),
    _case(
        "set_collection_alias",
        "repoint_unconfirmed_writes_nothing",
        returns=lambda: {"collection_aliases.list": [[_alias("chat", OTHER_CID)]]},
        name="chat",
        collection_id=CID,
    ),
    _case(
        "set_collection_alias",
        "repoint_confirmed_is_written",
        returns=lambda: {"collection_aliases.list": [[_alias("chat", OTHER_CID)]]},
        name="chat",
        collection_id=CID,
        confirm=True,
    ),
    _case(
        "set_collection_alias",
        "same_target_is_rewritten",
        returns=lambda: {"collection_aliases.list": [[_alias("chat", CID)]]},
        name="chat",
        collection_id=CID,
    ),
    _case("delete_collection_alias", name="chat"),
    # ---- config versions
    _case("list_config_versions", collection_id=CID),
    _case("list_config_versions", "paged", collection_id=CID, limit=5, offset=10),
    _case("get_config_version", collection_id=CID, version=3),
    _case("diff_config_versions", collection_id=CID, from_version=2, to_version=3),
    _case(
        "restore_config_version",
        "unconfirmed_diffs_head_against_target",
        returns=lambda: {"config_versions.list": [FakeModel(items=[FakeModel(version=7)])]},
        collection_id=CID,
        version=3,
    ),
    _case(
        "restore_config_version", "confirmed_restores", collection_id=CID, version=3, confirm=True
    ),
    # ---- corpus (grid + bulk operations)
    _case("query_documents", collection_id=CID),
    _case(
        "query_documents",
        "filtered_sorted_paged",
        collection_id=CID,
        filter=_FILTER,
        sort={"field": "created_at", "direction": "desc"},
        limit=10,
        offset=20,
    ),
    _case("delete_documents", "by_ids", collection_id=CID, selector={"document_ids": [DOC]}),
    _case(
        "delete_documents",
        "by_filter_with_exclusions",
        collection_id=CID,
        selector={"filter": _FILTER, "exclude_ids": ["doc-9"]},
    ),
    _case(
        "set_documents_enabled",
        collection_id=CID,
        selector={"document_ids": [DOC]},
        enabled=False,
    ),
    _case("reingest_documents", collection_id=CID, selector={"document_ids": [DOC]}),
    _case(
        "reingest_documents",
        "forced_replayed_confirmed",
        collection_id=CID,
        selector={"filter": _FILTER},
        force=True,
        replay_from="chunk",
        confirm_estimate=True,
    ),
    # ---- documents
    _case(
        "upload_document",
        file_path="/inbox/report.pdf",
        collection_id=CID,
        metadata={"year": 2024},
    ),
    _case("upload_document", "without_metadata", file_path="/inbox/report.pdf", collection_id=CID),
    _case(
        "upload_document_bytes",
        collection_id=CID,
        filename="report.pdf",
        content_base64=base64.b64encode(b"%PDF-1.7 fixed bytes").decode(),
        metadata={"year": 2024},
    ),
    _case("set_document_enabled", document_id=DOC, enabled=True),
    _case("update_document_metadata", document_id=DOC, values={"year": 2025, "tags": ["a", "b"]}),
    _case("get_document_markdown", document_id=DOC),
    _case("get_document_markdown", "pages", document_id=DOC, pages="5-7"),
    _case("get_document_html", document_id=DOC),
    _case("get_document_html", "pages", document_id=DOC, pages="5,7-9"),
    _case("reingest_document", document_id=DOC),
    _case("reingest_document", "forced_replayed", document_id=DOC, force=True, replay_from="embed"),
    _case("purge_document_trace_payloads", document_id=DOC),
    # ---- explorer
    _case("list_documents", collection_id=CID),
    _case("list_documents", "paged", collection_id=CID, limit=50, offset=100),
    _case("get_document", document_id=DOC),
    _case("get_document_pages", document_id=DOC),
    _case("get_document_ir", document_id=DOC),
    _case("get_document_provenance", document_id=DOC),
    _case("get_document_outline", document_id=DOC),
    _case("get_chunk_context", chunk_id="chunk-1"),
    _case("get_chunk_context", "window", chunk_id="chunk-1", before=3, after=0),
    _case("get_document_chunks", document_id=DOC),
    _case(
        "get_document_chunks",
        "paged_with_geometry",
        document_id=DOC,
        limit=100,
        offset=40,
        include_geometry=True,
    ),
    _case("delete_document", document_id=DOC),
    _case("set_chunk_enabled", chunk_id="chunk-1", enabled=False),
    _case("set_chunks_enabled", chunk_ids=["chunk-1", "chunk-2"], enabled=True),
    # ---- search
    _case("search_collection", collection_id=CID, query="termination clause"),
    _case(
        "search_collection",
        "every_option",
        collection_id=CID,
        query="termination clause",
        limit=25,
        filters={
            "topic": "legal",
            "tags": ["a", "b"],
            "year": {"gte": 2023, "lt": 2026},
            "status": {"not": "draft"},
            "kind": {"in": ["x", "y"]},
            "title": {"contains": "audit"},
            "owner": {"exists": True},
        },
        search_in=[
            {"field": "content", "semantic": True, "lexical": False},
            {"field": "topic", "semantic": False, "lexical": True},
        ],
        return_fields=["text", "metadata.topic"],
        group_by="document",
        max_per_document=3,
        min_score=0.25,
        rerank=False,
        fusion="dbsf",
        debug=True,
        format="json",
    ),
    _case("browse_chunks", collection_id=CID),
    _case(
        "browse_chunks",
        "filtered_paged",
        collection_id=CID,
        filters={"doc_id": DOC, "page": {"gte": 2}},
        limit=100,
        cursor="cursor-1",
        return_fields=["text"],
        format="json",
    ),
    _case("get_search_health"),
    # ---- jobs
    _case("list_jobs"),
    _case(
        "list_jobs",
        "every_filter",
        collection_id=CID,
        status=["failed", "cancelled"],
        order="oldest",
        limit=10,
        offset=20,
        stage="embed",
        error_type="timeout",
        search="job-",
        created_after="2026-01-01T00:00:00Z",
        created_before="2026-02-01T00:00:00Z",
        sort="duration",
    ),
    _case("get_failure_breakdown"),
    _case("get_failure_breakdown", "scoped_window", collection_id=CID, window_hours=48),
    _case("get_new_failures", since=_ISO),
    _case(
        "get_new_failures",
        "scoped_with_ids",
        since=_ISO,
        collection_id=CID,
        include_ids=True,
        limit=5,
    ),
    _case("get_job_timeseries"),
    _case("get_job_timeseries", "scoped_window", collection_id=CID, window_hours=72),
    _case("get_job", job_id=JOB),
    _case(
        "wait_for_job",
        "terminal_job_is_returned_after_one_poll",
        returns=lambda: {"jobs.get": [FakeModel(status="done", job_id=JOB)]},
        job_id=JOB,
    ),
    _case(
        "wait_for_job",
        "expired_deadline_returns_the_running_job",
        returns=lambda: {"jobs.get": [FakeModel(status="running", job_id=JOB)]},
        job_id=JOB,
        timeout_s=0.0,
    ),
    _case("get_job_events", job_id=JOB),
    _case("get_job_event_payload", job_id=JOB, event_id="event-1"),
    _case("get_job_event_payload", "input_slot", job_id=JOB, event_id="event-1", slot="input"),
    _case("get_live_workers"),
    _case("cancel_job", job_id=JOB),
    _case("cancel_job", "forced", job_id=JOB, force=True),
    _case("get_collection_cost", collection_id=CID),
    _case("get_queue_depth"),
    _case("get_queue_depth", "one_collection", collection_id=CID),
    _case("get_stage_durations", collection_id=CID),
    # ---- audit
    _case("list_audit"),
    _case(
        "list_audit",
        "every_filter",
        limit=10,
        cursor="cursor-1",
        actor_user_id="user-1",
        actor_key_id=KEY,
        target_type="collection",
        target_id=CID,
        correlation_id="corr-1",
        created_from="2026-01-01T00:00:00+00:00",
        created_to="2026-02-01T00:00:00+00:00",
    ),
    # ---- blobs
    _case("get_blob", content_hash="a" * 64),
    _case(
        "get_blob",
        "image_is_returned_inline",
        returns=lambda: {
            "blobs.get": [FakeModel(mime_type="image/png", content=b"\x89PNG fixed", dump={})]
        },
        content_hash="a" * 64,
    ),
    _case(
        "get_blob",
        "other_mime_is_returned_as_base64",
        returns=lambda: {
            "blobs.get": [FakeModel(mime_type="application/pdf", content=b"%PDF fixed", dump={})]
        },
        content_hash="b" * 64,
    ),
    # ---- pipelines
    _case("list_pipeline_surfaces"),
    _case("get_pipeline_design", key="ingest"),
    _case("get_pipeline_design", "full", key="search", full=True),
    _case("inspect_pipeline", key="ingest", blob=_PIPELINE_BLOB),
    _case(
        "edit_pipeline",
        key="ingest",
        blob=_PIPELINE_BLOB,
        operations=[{"op": "remove_node", "node_id": "parse"}],
    ),
    _case("view_pipeline_stages", key="ingest", blob=_PIPELINE_BLOB),
    _case(
        "apply_pipeline_stage",
        key="ingest",
        blob=_PIPELINE_BLOB,
        action={"action": "set_config", "stage": "chunk", "config": {"size": 400}},
    ),
    _case(
        "apply_collection_stage",
        "set_config_defaults_to_merge",
        collection_id=CID,
        action={"action": "set_config", "stage": "chunk", "config": {"size": 400}},
    ),
    _case(
        "apply_collection_stage",
        "set_config_keeps_an_explicit_mode",
        collection_id=CID,
        action={"action": "set_config", "stage": "chunk", "config": {}, "mode": "replace"},
        note="reset",
    ),
    _case(
        "apply_collection_stage",
        "other_action_is_sent_as_is",
        collection_id=CID,
        action={"action": "set_provider", "stage": "embed", "slot": "sparse", "kind": "bm25_local"},
    ),
    # ---- transfers
    _case("export_collection", collection_id=CID),
    _case("import_collection", file_path="/inbox/bundle.dcexport"),
    _case(
        "import_collection",
        "renamed",
        file_path="/inbox/bundle.dcexport",
        target_name="Imported",
    ),
    _case(
        "import_collection_bytes",
        content_base64=base64.b64encode(b"dcexport fixed bytes").decode(),
        target_name="Imported",
    ),
    _case("get_transfer", transfer_id="transfer-1"),
    _case(
        "get_export_download_ref",
        returns=lambda: {
            "transfers.get_transfer": [
                FakeModel(
                    transfer_id="transfer-1",
                    kind="export",
                    status="done",
                    size_bytes=1234,
                    expires_at=None,
                )
            ]
        },
        transfer_id="transfer-1",
    ),
)
