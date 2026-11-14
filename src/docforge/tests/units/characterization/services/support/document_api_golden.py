# ====== Code Summary ======
# Golden: what every DocumentApi method sends to the database TODAY, as the operations a RecordingSession
# records (compiled PostgreSQL statements, ORM gets/adds/deletes/flushes, attribute writes), one entry
# per call spec of ``document_call_specs.py``. An empty entry means the call is a recorded no-op. Recorded on main
# before the data-layer refactoring campaign: a diff here is a behaviour change, not a formatting
# nit — review it as one.

#: ``method`` or ``method[variant]`` -> the rendered operations of that call.
DOCUMENT_API_GOLDEN: dict[str, str] = {
    "count_by_collections": """execute:
SELECT document.collection_id, count(*) AS count_1
FROM document
WHERE document.collection_id IN (__[POSTCOMPILE_collection_id_1]) GROUP BY document.collection_id""",
    "count_for_collection": """execute:
SELECT count(*) AS count_1
FROM document
WHERE document.collection_id = %(collection_id_1)s::UUID""",
    "count_for_collection[status]": """execute:
SELECT count(*) AS count_1
FROM document
WHERE document.collection_id = %(collection_id_1)s::UUID AND document.status = %(status_1)s""",
    "create": """add:Document
--
flush""",
    "delete": """get:Document
--
delete:_TrackedEntity""",
    "delete_many": """execute:
DELETE FROM document WHERE document.id IN (__[POSTCOMPILE_id_1])""",
    "delete_many[empty]": """""",
    "delete_metadata": """execute:
DELETE FROM document_metadata WHERE document_metadata.document_id = %(document_id_1)s::UUID AND document_metadata.field_id IN (__[POSTCOMPILE_field_id_1])""",
    "delete_metadata[empty]": """""",
    "finalize_done": """get:Document
--
set:Document.status=<DocumentStatus.DONE: 'done'>
--
set:Document.warning_reason=None
--
set:Document.chunk_count=12""",
    "finalize_done[warning-no-count]": """get:Document
--
set:Document.status=<DocumentStatus.DONE: 'done'>
--
set:Document.warning_reason='0 chunks'""",
    "finalize_done[cancelled-untouched]": """get:Document""",
    "find": """execute:
SELECT document.collection_id, document.source_hash, document.pdf_blob_hash, document.filename, document.format, document.mime_type, document.file_size, document.page_count, document.language, document.source_kind, document.title, document.simhash, document.status, document.pipeline_version, document.enabled, document.warning_reason, document.chunk_count, document.id, document.created_at, document.updated_at
FROM document
WHERE document.collection_id = %(collection_id_1)s::UUID AND document.source_hash = %(source_hash_1)s::VARCHAR AND document.pipeline_version = %(pipeline_version_1)s::VARCHAR""",
    "flag_replay_failure[pending-falls-back-to-failed]": """get:Document
--
set:Document.status=<DocumentStatus.FAILED: 'failed'>
--
set:Document.warning_reason='replay failed'""",
    "flag_replay_failure[done-keeps-status]": """get:Document
--
set:Document.warning_reason='replay failed'""",
    "get": """get:Document""",
    "get_by_ids": """execute:
SELECT document.collection_id, document.source_hash, document.pdf_blob_hash, document.filename, document.format, document.mime_type, document.file_size, document.page_count, document.language, document.source_kind, document.title, document.simhash, document.status, document.pipeline_version, document.enabled, document.warning_reason, document.chunk_count, document.id, document.created_at, document.updated_at
FROM document
WHERE document.id IN (__[POSTCOMPILE_id_1])""",
    "get_by_ids[empty]": """""",
    "get_chunk_filterable_metadata": """execute:
SELECT chunk_metadata.chunk_id, metadata_field.field_name, chunk_metadata.value
FROM chunk_metadata JOIN metadata_field ON metadata_field.id = chunk_metadata.field_id JOIN chunk ON chunk.id = chunk_metadata.chunk_id
WHERE chunk.document_id = %(document_id_1)s::UUID AND metadata_field.filterable IS true AND metadata_field.scope = %(scope_1)s""",
    "get_filterable_metadata": """execute:
SELECT metadata_field.field_name, document_metadata.value
FROM document_metadata JOIN metadata_field ON metadata_field.id = document_metadata.field_id
WHERE document_metadata.document_id = %(document_id_1)s::UUID AND metadata_field.filterable IS true AND metadata_field.scope = %(scope_1)s""",
    "get_filterable_metadata_for_documents": """execute:
SELECT document_metadata.document_id, metadata_field.field_name, document_metadata.value
FROM document_metadata JOIN metadata_field ON metadata_field.id = document_metadata.field_id
WHERE document_metadata.document_id IN (__[POSTCOMPILE_document_id_1]) AND metadata_field.filterable IS true AND metadata_field.scope = %(scope_1)s""",
    "get_for_update": """get:Document""",
    "get_metadata": """execute:
SELECT document_metadata.id, document_metadata.document_id, document_metadata.field_id, document_metadata.value, document_metadata.origin
FROM document_metadata
WHERE document_metadata.document_id = %(document_id_1)s::UUID""",
    "get_metadata_for_documents": """execute:
SELECT document_metadata.id, document_metadata.document_id, document_metadata.field_id, document_metadata.value, document_metadata.origin
FROM document_metadata
WHERE document_metadata.document_id IN (__[POSTCOMPILE_document_id_1])""",
    "get_metadata_with_names": """execute:
SELECT metadata_field.field_name, document_metadata.value, document_metadata.origin
FROM document_metadata JOIN metadata_field ON metadata_field.id = document_metadata.field_id
WHERE document_metadata.document_id = %(document_id_1)s::UUID""",
    "get_pages": """execute:
SELECT page.document_id, page.page_number, page.width, page.height, page.is_scanned, page.language, page.render_blob_hash, page.id
FROM page
WHERE page.document_id = %(document_id_1)s::UUID ORDER BY page.page_number""",
    "get_searchable_metadata": """execute:
SELECT metadata_field.field_name, document_metadata.value, metadata_field.semantic, metadata_field.lexical
FROM document_metadata JOIN metadata_field ON metadata_field.id = document_metadata.field_id
WHERE document_metadata.document_id = %(document_id_1)s::UUID AND metadata_field.scope = %(scope_1)s AND (metadata_field.semantic IS true OR metadata_field.lexical IS true)""",
    "list_disabled_ids": """execute:
SELECT document.id
FROM document
WHERE document.collection_id = %(collection_id_1)s::UUID AND document.enabled IS false""",
    "list_disabled_ids[limit]": """execute:
SELECT document.id
FROM document
WHERE document.collection_id = %(collection_id_1)s::UUID AND document.enabled IS false
LIMIT %(param_1)s::INTEGER""",
    "list_enabled_ids": """execute:
SELECT document.id
FROM document
WHERE document.collection_id = %(collection_id_1)s::UUID AND document.enabled IS true""",
    "list_for_collection": """execute:
SELECT document.collection_id, document.source_hash, document.pdf_blob_hash, document.filename, document.format, document.mime_type, document.file_size, document.page_count, document.language, document.source_kind, document.title, document.simhash, document.status, document.pipeline_version, document.enabled, document.warning_reason, document.chunk_count, document.id, document.created_at, document.updated_at
FROM document
WHERE document.collection_id = %(collection_id_1)s::UUID ORDER BY document.created_at DESC, document.id DESC
LIMIT ALL OFFSET %(param_1)s::INTEGER""",
    "list_for_collection[status-page]": """execute:
SELECT document.collection_id, document.source_hash, document.pdf_blob_hash, document.filename, document.format, document.mime_type, document.file_size, document.page_count, document.language, document.source_kind, document.title, document.simhash, document.status, document.pipeline_version, document.enabled, document.warning_reason, document.chunk_count, document.id, document.created_at, document.updated_at
FROM document
WHERE document.collection_id = %(collection_id_1)s::UUID AND document.status = %(status_1)s ORDER BY document.created_at DESC, document.id DESC
LIMIT %(param_1)s::INTEGER OFFSET %(param_2)s::INTEGER""",
    "mark_processing": """get:Document
--
set:Document.status=<DocumentStatus.PROCESSING: 'processing'>""",
    "mark_processing[done-untouched]": """get:Document""",
    "replace_metadata": """execute:
DELETE FROM document_metadata WHERE document_metadata.document_id = %(document_id_1)s::UUID AND document_metadata.origin = %(origin_1)s
--
add_all:DocumentMetadata,DocumentMetadata""",
    "replace_pages": """execute:
DELETE FROM page WHERE page.document_id = %(document_id_1)s::UUID
--
add_all:Page,Page,Page""",
    "set_enabled": """get:Document
--
set:Document.enabled=False""",
    "set_enabled_many": """execute:
UPDATE document SET enabled=%(enabled)s, updated_at=now() WHERE document.id IN (__[POSTCOMPILE_id_1]) AND document.enabled IS false""",
    "set_enabled_many[empty]": """""",
    "set_status": """get:Document
--
set:Document.status=<DocumentStatus.FAILED: 'failed'>""",
    "touch": """execute:
UPDATE document SET updated_at=clock_timestamp() WHERE document.id = %(id_1)s::UUID""",
    "update_facts": """get:Document
--
set:Document.title='T'
--
set:Document.language='fr'
--
set:Document.page_count=3""",
    "update_facts[all-fields]": """get:Document
--
set:Document.title='T'
--
set:Document.language='fr'
--
set:Document.page_count=3
--
set:Document.source_kind=<SourceKind.DIGITAL_BORN: 'digital_born'>
--
set:Document.pdf_blob_hash='blob1'
--
set:Document.simhash='sim1'""",
    "update_metadata": """execute:
INSERT INTO document_metadata (document_id, field_id, value, origin) VALUES (%(document_id_m0)s::UUID, %(field_id_m0)s::INTEGER, %(value_m0)s::JSONB, %(origin_m0)s) ON CONFLICT (document_id, field_id) DO UPDATE SET value = excluded.value, origin = excluded.origin""",
    "update_metadata[empty]": """""",
}
