# ====== Code Summary ======
# The fixed-argument call table for every public DocumentApi method. One spec per method (plus
# variants where a branch or a guarded state transition changes what is sent to the database), each
# built from constants only so the compiled statements are deterministic.

# ====== Standard Library Imports ======

# ====== Internal Project Imports ======
from shared_libs.services.db.postgresql.apis.document_api import DocumentApi
from shared_libs.services.db.postgresql.tables import (
    Document,
    DocumentMetadata,
    DocumentStatus,
    Page,
    SourceKind,
)

# ====== Local Project Imports ======
from .api_runner import CallSpec
from .job_call_specs import COLLECTION_ID, COLLECTION_ID_2, DOC_ID, DOC_ID_2

#: Public methods characterized by NAME ONLY (none: every DocumentApi method records operations).
NAME_ONLY: frozenset[str] = frozenset()

_UPSERT_ROW = DocumentMetadata(field_id=7, value="v", origin="user")

DOCUMENT_SPECS: tuple[CallSpec, ...] = (
    CallSpec(
        "count_by_collections",
        "",
        lambda s: DocumentApi.count_by_collections(s, [COLLECTION_ID, COLLECTION_ID_2]),
    ),
    CallSpec(
        "count_for_collection", "", lambda s: DocumentApi.count_for_collection(s, COLLECTION_ID)
    ),
    CallSpec(
        "count_for_collection",
        "status",
        lambda s: DocumentApi.count_for_collection(s, COLLECTION_ID, DocumentStatus.DONE),
    ),
    CallSpec("create", "", lambda s: DocumentApi.create(s, Document())),
    CallSpec("delete", "", lambda s: DocumentApi.delete(s, DOC_ID)),
    CallSpec("delete_many", "", lambda s: DocumentApi.delete_many(s, [DOC_ID, DOC_ID_2])),
    CallSpec("delete_many", "empty", lambda s: DocumentApi.delete_many(s, [])),
    CallSpec("delete_metadata", "", lambda s: DocumentApi.delete_metadata(s, DOC_ID, [1, 2])),
    CallSpec("delete_metadata", "empty", lambda s: DocumentApi.delete_metadata(s, DOC_ID, [])),
    CallSpec(
        "finalize_done",
        "",
        lambda s: DocumentApi.finalize_done(s, DOC_ID, chunk_count=12),
        {"status": DocumentStatus.PROCESSING},
    ),
    CallSpec(
        "finalize_done",
        "warning-no-count",
        lambda s: DocumentApi.finalize_done(s, DOC_ID, warning_reason="0 chunks"),
        {"status": DocumentStatus.PROCESSING},
    ),
    CallSpec(
        "finalize_done",
        "cancelled-untouched",
        lambda s: DocumentApi.finalize_done(s, DOC_ID, chunk_count=12),
        {"status": DocumentStatus.CANCELLED},
    ),
    CallSpec("find", "", lambda s: DocumentApi.find(s, COLLECTION_ID, "abc123", "v1")),
    CallSpec(
        "flag_replay_failure",
        "pending-falls-back-to-failed",
        lambda s: DocumentApi.flag_replay_failure(s, DOC_ID, "replay failed"),
        {"status": DocumentStatus.PENDING},
    ),
    CallSpec(
        "flag_replay_failure",
        "done-keeps-status",
        lambda s: DocumentApi.flag_replay_failure(s, DOC_ID, "replay failed"),
        {"status": DocumentStatus.DONE},
    ),
    CallSpec("get", "", lambda s: DocumentApi.get(s, DOC_ID)),
    CallSpec("get_by_ids", "", lambda s: DocumentApi.get_by_ids(s, [DOC_ID, DOC_ID_2])),
    CallSpec("get_by_ids", "empty", lambda s: DocumentApi.get_by_ids(s, [])),
    CallSpec(
        "get_chunk_filterable_metadata",
        "",
        lambda s: DocumentApi.get_chunk_filterable_metadata(s, DOC_ID),
    ),
    CallSpec(
        "get_filterable_metadata", "", lambda s: DocumentApi.get_filterable_metadata(s, DOC_ID)
    ),
    CallSpec(
        "get_filterable_metadata_for_documents",
        "",
        lambda s: DocumentApi.get_filterable_metadata_for_documents(s, [DOC_ID, DOC_ID_2]),
    ),
    CallSpec("get_for_update", "", lambda s: DocumentApi.get_for_update(s, DOC_ID)),
    CallSpec("get_metadata", "", lambda s: DocumentApi.get_metadata(s, DOC_ID)),
    CallSpec(
        "get_metadata_for_documents",
        "",
        lambda s: DocumentApi.get_metadata_for_documents(s, [DOC_ID, DOC_ID_2]),
    ),
    CallSpec(
        "get_metadata_with_names", "", lambda s: DocumentApi.get_metadata_with_names(s, DOC_ID)
    ),
    CallSpec("get_pages", "", lambda s: DocumentApi.get_pages(s, DOC_ID)),
    CallSpec(
        "get_searchable_metadata", "", lambda s: DocumentApi.get_searchable_metadata(s, DOC_ID)
    ),
    CallSpec("list_disabled_ids", "", lambda s: DocumentApi.list_disabled_ids(s, COLLECTION_ID)),
    CallSpec(
        "list_disabled_ids", "limit", lambda s: DocumentApi.list_disabled_ids(s, COLLECTION_ID, 5)
    ),
    CallSpec("list_enabled_ids", "", lambda s: DocumentApi.list_enabled_ids(s, COLLECTION_ID)),
    CallSpec(
        "list_for_collection", "", lambda s: DocumentApi.list_for_collection(s, COLLECTION_ID)
    ),
    CallSpec(
        "list_for_collection",
        "status-page",
        lambda s: DocumentApi.list_for_collection(s, COLLECTION_ID, DocumentStatus.FAILED, 10, 20),
    ),
    CallSpec(
        "mark_processing",
        "",
        lambda s: DocumentApi.mark_processing(s, DOC_ID),
        {"status": DocumentStatus.PENDING},
    ),
    CallSpec(
        "mark_processing",
        "done-untouched",
        lambda s: DocumentApi.mark_processing(s, DOC_ID),
        {"status": DocumentStatus.DONE},
    ),
    CallSpec(
        "replace_metadata",
        "",
        lambda s: DocumentApi.replace_metadata(s, DOC_ID, [DocumentMetadata(), DocumentMetadata()]),
    ),
    CallSpec(
        "replace_pages",
        "",
        lambda s: DocumentApi.replace_pages(s, DOC_ID, [Page(), Page(), Page()]),
    ),
    CallSpec("set_enabled", "", lambda s: DocumentApi.set_enabled(s, DOC_ID, False)),
    CallSpec(
        "set_enabled_many", "", lambda s: DocumentApi.set_enabled_many(s, [DOC_ID, DOC_ID_2], True)
    ),
    CallSpec("set_enabled_many", "empty", lambda s: DocumentApi.set_enabled_many(s, [], True)),
    CallSpec(
        "set_status",
        "",
        lambda s: DocumentApi.set_status(s, DOC_ID, DocumentStatus.FAILED),
    ),
    CallSpec("touch", "", lambda s: DocumentApi.touch(s, DOC_ID)),
    CallSpec(
        "update_facts",
        "",
        lambda s: DocumentApi.update_facts(s, DOC_ID, title="T", language="fr", page_count=3),
    ),
    CallSpec(
        "update_facts",
        "all-fields",
        lambda s: DocumentApi.update_facts(
            s,
            DOC_ID,
            title="T",
            language="fr",
            page_count=3,
            source_kind=SourceKind.DIGITAL_BORN,
            pdf_blob_hash="blob1",
            simhash="sim1",
        ),
    ),
    CallSpec(
        "update_metadata", "", lambda s: DocumentApi.update_metadata(s, DOC_ID, [_UPSERT_ROW])
    ),
    CallSpec("update_metadata", "empty", lambda s: DocumentApi.update_metadata(s, DOC_ID, [])),
)
