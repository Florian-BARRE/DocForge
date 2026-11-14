# ====== Code Summary ======
# Golden: what every JobApi method sends to the database TODAY, as the operations a RecordingSession
# records (compiled PostgreSQL statements, ORM gets/adds/deletes/flushes, attribute writes), one entry
# per call spec of ``job_call_specs.py``. An empty entry means the call is a recorded no-op. Recorded on main
# before the data-layer refactoring campaign: a diff here is a behaviour change, not a formatting
# nit — review it as one.

#: ``method`` or ``method[variant]`` -> the rendered operations of that call.
JOB_API_GOLDEN: dict[str, str] = {
    "add_usage": """execute:
UPDATE job SET total_prompt_tokens=(job.total_prompt_tokens + %(total_prompt_tokens_1)s::BIGINT), total_completion_tokens=(job.total_completion_tokens + %(total_completion_tokens_1)s::BIGINT), cost_usd=(job.cost_usd + %(cost_usd_1)s), updated_at=now() WHERE job.id = %(id_1)s::UUID""",
    "add_usage[no-cost]": """execute:
UPDATE job SET total_prompt_tokens=(job.total_prompt_tokens + %(total_prompt_tokens_1)s::BIGINT), total_completion_tokens=(job.total_completion_tokens + %(total_completion_tokens_1)s::BIGINT), cost_usd=(job.cost_usd + %(cost_usd_1)s), updated_at=now() WHERE job.id = %(id_1)s::UUID""",
    "avg_stage_durations": """execute:
SELECT job_stage_event.stage, avg(EXTRACT(epoch FROM job_stage_event.finished_at - job_stage_event.started_at)) AS avg_1
FROM job_stage_event JOIN job ON job.id = job_stage_event.job_id
WHERE job.collection_id = %(collection_id_1)s::UUID AND job.status = %(status_1)s AND job_stage_event.started_at IS NOT NULL AND job_stage_event.finished_at IS NOT NULL GROUP BY job_stage_event.stage""",
    "clear_trace_refs": """execute:
UPDATE job_stage_event SET input_ref=%(input_ref)s::VARCHAR, output_ref=%(output_ref)s::VARCHAR, has_full_input=%(has_full_input)s, has_full_output=%(has_full_output)s WHERE job_stage_event.job_id IN (__[POSTCOMPILE_job_id_1])
--
execute:
UPDATE job SET trace_payload_bytes=%(trace_payload_bytes)s::BIGINT, updated_at=now() WHERE job.id IN (__[POSTCOMPILE_id_1])""",
    "clear_trace_refs[empty]": """""",
    "collection_cost": """execute:
SELECT coalesce(sum(job.total_prompt_tokens), %(coalesce_2)s::INTEGER) AS coalesce_1, coalesce(sum(job.total_completion_tokens), %(coalesce_4)s::INTEGER) AS coalesce_3, coalesce(sum(job.cost_usd), %(coalesce_6)s::INTEGER) AS coalesce_5, count(job.id) AS count_1
FROM job
WHERE job.collection_id = %(collection_id_1)s::UUID""",
    "count_failed_since": """execute:
SELECT count(*) AS count_1, max(job.finished_at) AS max_1
FROM job
WHERE job.status = %(status_1)s AND job.finished_at > %(finished_at_1)s::TIMESTAMP WITH TIME ZONE""",
    "count_failed_since[collection]": """execute:
SELECT count(*) AS count_1, max(job.finished_at) AS max_1
FROM job
WHERE job.status = %(status_1)s AND job.finished_at > %(finished_at_1)s::TIMESTAMP WITH TIME ZONE AND job.collection_id = %(collection_id_1)s::UUID""",
    "count_for_collection": """execute:
SELECT count(*) AS count_1
FROM job
WHERE job.collection_id = %(collection_id_1)s::UUID""",
    "count_jobs": """execute:
SELECT count(*) AS count_1
FROM job""",
    "count_jobs[all-filters]": """execute:
SELECT count(*) AS count_1
FROM job
WHERE job.collection_id = %(collection_id_1)s::UUID AND job.status IN (__[POSTCOMPILE_status_1]) AND job.current_stage = %(current_stage_1)s::VARCHAR AND job.error_type = %(error_type_1)s::VARCHAR AND job.created_at >= %(created_at_1)s::TIMESTAMP WITH TIME ZONE AND job.created_at <= %(created_at_2)s::TIMESTAMP WITH TIME ZONE AND (CAST(job.id AS VARCHAR) ILIKE %(param_1)s::VARCHAR OR CAST(job.document_id AS VARCHAR) ILIKE %(param_2)s::VARCHAR)""",
    "create": """add:Job
--
flush""",
    "delete_heartbeat": """execute:
DELETE FROM worker_heartbeats WHERE worker_heartbeats.worker_id = %(worker_id_1)s::VARCHAR""",
    "events_query": """statement:
SELECT job_stage_event.job_id, job_stage_event.stage, job_stage_event.status, job_stage_event.node_kind, job_stage_event.started_at, job_stage_event.finished_at, job_stage_event.detail, job_stage_event.prompt_tokens, job_stage_event.completion_tokens, job_stage_event.cost_usd, job_stage_event.node_path, job_stage_event.depth, job_stage_event.parent_path, job_stage_event.item_index, job_stage_event.score, job_stage_event.input_summary, job_stage_event.output_summary, job_stage_event.input_ref, job_stage_event.output_ref, job_stage_event.has_full_input, job_stage_event.has_full_output, job_stage_event.id, job_stage_event.created_at
FROM job_stage_event
WHERE job_stage_event.job_id = %(job_id_1)s::UUID""",
    "events_query[lean-after]": """statement:
SELECT job_stage_event.job_id, job_stage_event.stage, job_stage_event.status, job_stage_event.node_kind, job_stage_event.started_at, job_stage_event.finished_at, job_stage_event.detail, job_stage_event.prompt_tokens, job_stage_event.completion_tokens, job_stage_event.cost_usd, job_stage_event.node_path, job_stage_event.depth, job_stage_event.parent_path, job_stage_event.item_index, job_stage_event.score, job_stage_event.input_ref, job_stage_event.output_ref, job_stage_event.has_full_input, job_stage_event.has_full_output, job_stage_event.id, job_stage_event.created_at
FROM job_stage_event
WHERE job_stage_event.job_id = %(job_id_1)s::UUID AND job_stage_event.created_at > %(created_at_1)s::TIMESTAMP WITH TIME ZONE""",
    "failure_breakdown": """execute:
SELECT count(*) AS count_1
FROM job
WHERE job.status = %(status_1)s AND job.created_at >= %(created_at_1)s::TIMESTAMP WITH TIME ZONE
--
execute:
SELECT job.error_type, count(*) AS count_1
FROM job
WHERE job.status = %(status_1)s AND job.created_at >= %(created_at_1)s::TIMESTAMP WITH TIME ZONE GROUP BY job.error_type ORDER BY count(*) DESC
LIMIT %(param_1)s::INTEGER
--
execute:
SELECT job.current_stage, count(*) AS count_1
FROM job
WHERE job.status = %(status_1)s AND job.created_at >= %(created_at_1)s::TIMESTAMP WITH TIME ZONE GROUP BY job.current_stage ORDER BY count(*) DESC
LIMIT %(param_1)s::INTEGER
--
execute:
SELECT job.collection_id, collection.name, count(*) AS count_1
FROM job LEFT OUTER JOIN collection ON collection.id = job.collection_id
WHERE job.status = %(status_1)s AND job.created_at >= %(created_at_1)s::TIMESTAMP WITH TIME ZONE GROUP BY job.collection_id, collection.name ORDER BY count(*) DESC
LIMIT %(param_1)s::INTEGER""",
    "failure_breakdown[collection-top3]": """execute:
SELECT count(*) AS count_1
FROM job
WHERE job.status = %(status_1)s AND job.created_at >= %(created_at_1)s::TIMESTAMP WITH TIME ZONE AND job.collection_id = %(collection_id_1)s::UUID
--
execute:
SELECT job.error_type, count(*) AS count_1
FROM job
WHERE job.status = %(status_1)s AND job.created_at >= %(created_at_1)s::TIMESTAMP WITH TIME ZONE AND job.collection_id = %(collection_id_1)s::UUID GROUP BY job.error_type ORDER BY count(*) DESC
LIMIT %(param_1)s::INTEGER
--
execute:
SELECT job.current_stage, count(*) AS count_1
FROM job
WHERE job.status = %(status_1)s AND job.created_at >= %(created_at_1)s::TIMESTAMP WITH TIME ZONE AND job.collection_id = %(collection_id_1)s::UUID GROUP BY job.current_stage ORDER BY count(*) DESC
LIMIT %(param_1)s::INTEGER
--
execute:
SELECT job.collection_id, collection.name, count(*) AS count_1
FROM job LEFT OUTER JOIN collection ON collection.id = job.collection_id
WHERE job.status = %(status_1)s AND job.created_at >= %(created_at_1)s::TIMESTAMP WITH TIME ZONE AND job.collection_id = %(collection_id_1)s::UUID GROUP BY job.collection_id, collection.name ORDER BY count(*) DESC
LIMIT %(param_1)s::INTEGER""",
    "finalize_event": """execute:
UPDATE job_stage_event SET status=%(status)s::VARCHAR, finished_at=%(finished_at)s::TIMESTAMP WITH TIME ZONE, detail=%(detail)s::VARCHAR, prompt_tokens=%(prompt_tokens)s::INTEGER, completion_tokens=%(completion_tokens)s::INTEGER, cost_usd=%(cost_usd)s WHERE job_stage_event.id = %(id_1)s::UUID""",
    "get": """get:Job""",
    "get_active_for_document": """execute:
SELECT job.document_id, job.collection_id, job.status, job.kind, job.cancel_requested, job.worker_id, job.attempt, job.current_stage, job.progress, job.error, job.started_at, job.finished_at, job.total_prompt_tokens, job.total_completion_tokens, job.cost_usd, job.trace_payload_bytes, job.items_done, job.items_total, job.failed_node_id, job.failed_node_kind, job.failed_item_index, job.error_type, job.replay_from, job.id, job.created_at, job.updated_at
FROM job
WHERE job.document_id = %(document_id_1)s::UUID AND job.status IN (__[POSTCOMPILE_status_1]) ORDER BY job.created_at DESC, job.id DESC
LIMIT %(param_1)s::INTEGER""",
    "get_event": """execute:
SELECT job_stage_event.job_id, job_stage_event.stage, job_stage_event.status, job_stage_event.node_kind, job_stage_event.started_at, job_stage_event.finished_at, job_stage_event.detail, job_stage_event.prompt_tokens, job_stage_event.completion_tokens, job_stage_event.cost_usd, job_stage_event.node_path, job_stage_event.depth, job_stage_event.parent_path, job_stage_event.item_index, job_stage_event.score, job_stage_event.input_summary, job_stage_event.output_summary, job_stage_event.input_ref, job_stage_event.output_ref, job_stage_event.has_full_input, job_stage_event.has_full_output, job_stage_event.id, job_stage_event.created_at
FROM job_stage_event
WHERE job_stage_event.id = %(id_1)s::UUID AND job_stage_event.job_id = %(job_id_1)s::UUID""",
    "get_latest_for_document": """execute:
SELECT job.document_id, job.collection_id, job.status, job.kind, job.cancel_requested, job.worker_id, job.attempt, job.current_stage, job.progress, job.error, job.started_at, job.finished_at, job.total_prompt_tokens, job.total_completion_tokens, job.cost_usd, job.trace_payload_bytes, job.items_done, job.items_total, job.failed_node_id, job.failed_node_kind, job.failed_item_index, job.error_type, job.replay_from, job.id, job.created_at, job.updated_at
FROM job
WHERE job.document_id = %(document_id_1)s::UUID ORDER BY job.created_at DESC, job.id DESC
LIMIT %(param_1)s::INTEGER""",
    "get_latest_successful_for_document": """execute:
SELECT job.document_id, job.collection_id, job.status, job.kind, job.cancel_requested, job.worker_id, job.attempt, job.current_stage, job.progress, job.error, job.started_at, job.finished_at, job.total_prompt_tokens, job.total_completion_tokens, job.cost_usd, job.trace_payload_bytes, job.items_done, job.items_total, job.failed_node_id, job.failed_node_kind, job.failed_item_index, job.error_type, job.replay_from, job.id, job.created_at, job.updated_at
FROM job
WHERE job.document_id = %(document_id_1)s::UUID AND job.status = %(status_1)s ORDER BY job.created_at DESC, job.id DESC
LIMIT %(param_1)s::INTEGER""",
    "get_with_names": """execute:
SELECT job.document_id, job.collection_id, job.status, job.kind, job.cancel_requested, job.worker_id, job.attempt, job.current_stage, job.progress, job.error, job.started_at, job.finished_at, job.total_prompt_tokens, job.total_completion_tokens, job.cost_usd, job.trace_payload_bytes, job.items_done, job.items_total, job.failed_node_id, job.failed_node_kind, job.failed_item_index, job.error_type, job.replay_from, job.id, job.created_at, job.updated_at, document.filename, document.title, collection.name, collection.title_field, (SELECT document_metadata.value
FROM document_metadata JOIN metadata_field ON metadata_field.id = document_metadata.field_id
WHERE document_metadata.document_id = job.document_id AND metadata_field.collection_id = job.collection_id AND metadata_field.field_name = collection.title_field AND metadata_field.scope = %(scope_1)s) AS anon_1
FROM job LEFT OUTER JOIN document ON document.id = job.document_id LEFT OUTER JOIN collection ON collection.id = job.collection_id
WHERE job.id = %(id_1)s::UUID""",
    "is_cancel_requested": """execute:
SELECT job.id, job.cancel_requested
FROM job
WHERE job.id = %(id_1)s::UUID""",
    "job_timeseries": """execute:
SELECT date_trunc(%(date_trunc_2)s::VARCHAR, job.created_at) AS date_trunc_1, count(*) AS count_1
FROM job
WHERE job.created_at >= %(created_at_1)s::TIMESTAMP WITH TIME ZONE GROUP BY date_trunc(%(date_trunc_2)s::VARCHAR, job.created_at)
--
execute:
SELECT date_trunc(%(date_trunc_2)s::VARCHAR, job.finished_at) AS date_trunc_1, job.status, count(*) AS count_1
FROM job
WHERE job.finished_at >= %(finished_at_1)s::TIMESTAMP WITH TIME ZONE AND job.status IN (__[POSTCOMPILE_status_1]) GROUP BY date_trunc(%(date_trunc_2)s::VARCHAR, job.finished_at), job.status
--
execute:
SELECT count(*) AS count_1
FROM job
WHERE job.created_at < %(created_at_1)s::TIMESTAMP WITH TIME ZONE AND (job.finished_at IS NULL OR job.finished_at >= %(finished_at_1)s::TIMESTAMP WITH TIME ZONE)""",
    "job_timeseries[collection]": """execute:
SELECT date_trunc(%(date_trunc_2)s::VARCHAR, job.created_at) AS date_trunc_1, count(*) AS count_1
FROM job
WHERE job.created_at >= %(created_at_1)s::TIMESTAMP WITH TIME ZONE AND job.collection_id = %(collection_id_1)s::UUID GROUP BY date_trunc(%(date_trunc_2)s::VARCHAR, job.created_at)
--
execute:
SELECT date_trunc(%(date_trunc_2)s::VARCHAR, job.finished_at) AS date_trunc_1, job.status, count(*) AS count_1
FROM job
WHERE job.finished_at >= %(finished_at_1)s::TIMESTAMP WITH TIME ZONE AND job.status IN (__[POSTCOMPILE_status_1]) AND job.collection_id = %(collection_id_1)s::UUID GROUP BY date_trunc(%(date_trunc_2)s::VARCHAR, job.finished_at), job.status
--
execute:
SELECT count(*) AS count_1
FROM job
WHERE job.created_at < %(created_at_1)s::TIMESTAMP WITH TIME ZONE AND (job.finished_at IS NULL OR job.finished_at >= %(finished_at_1)s::TIMESTAMP WITH TIME ZONE) AND job.collection_id = %(collection_id_1)s::UUID""",
    "last_successful_ingest_at": """execute:
SELECT max(job.finished_at) AS max_1
FROM job
WHERE job.collection_id = %(collection_id_1)s::UUID AND job.status = %(status_1)s AND job.kind != %(kind_1)s""",
    "last_successful_ingest_at_by_collections": """execute:
SELECT job.collection_id, max(job.finished_at) AS max_1
FROM job
WHERE job.collection_id IN (__[POSTCOMPILE_collection_id_1]) AND job.status = %(status_1)s AND job.kind != %(kind_1)s GROUP BY job.collection_id""",
    "list_active": """execute:
SELECT job.document_id, job.collection_id, job.status, job.kind, job.cancel_requested, job.worker_id, job.attempt, job.current_stage, job.progress, job.error, job.started_at, job.finished_at, job.total_prompt_tokens, job.total_completion_tokens, job.cost_usd, job.trace_payload_bytes, job.items_done, job.items_total, job.failed_node_id, job.failed_node_kind, job.failed_item_index, job.error_type, job.replay_from, job.id, job.created_at, job.updated_at
FROM job
WHERE job.status = %(status_1)s ORDER BY job.started_at ASC""",
    "list_active_for_collection": """execute:
SELECT job.document_id, job.collection_id, job.status, job.kind, job.cancel_requested, job.worker_id, job.attempt, job.current_stage, job.progress, job.error, job.started_at, job.finished_at, job.total_prompt_tokens, job.total_completion_tokens, job.cost_usd, job.trace_payload_bytes, job.items_done, job.items_total, job.failed_node_id, job.failed_node_kind, job.failed_item_index, job.error_type, job.replay_from, job.id, job.created_at, job.updated_at
FROM job
WHERE job.collection_id = %(collection_id_1)s::UUID AND job.status IN (__[POSTCOMPILE_status_1])""",
    "list_active_with_names": """execute:
SELECT job.document_id, job.collection_id, job.status, job.kind, job.cancel_requested, job.worker_id, job.attempt, job.current_stage, job.progress, job.error, job.started_at, job.finished_at, job.total_prompt_tokens, job.total_completion_tokens, job.cost_usd, job.trace_payload_bytes, job.items_done, job.items_total, job.failed_node_id, job.failed_node_kind, job.failed_item_index, job.error_type, job.replay_from, job.id, job.created_at, job.updated_at, document.filename, document.title, collection.name, collection.title_field, (SELECT document_metadata.value
FROM document_metadata JOIN metadata_field ON metadata_field.id = document_metadata.field_id
WHERE document_metadata.document_id = job.document_id AND metadata_field.collection_id = job.collection_id AND metadata_field.field_name = collection.title_field AND metadata_field.scope = %(scope_1)s) AS anon_1
FROM job LEFT OUTER JOIN document ON document.id = job.document_id LEFT OUTER JOIN collection ON collection.id = job.collection_id
WHERE job.status = %(status_1)s ORDER BY job.started_at ASC""",
    "list_events": """execute:
SELECT job_stage_event.job_id, job_stage_event.stage, job_stage_event.status, job_stage_event.node_kind, job_stage_event.started_at, job_stage_event.finished_at, job_stage_event.detail, job_stage_event.prompt_tokens, job_stage_event.completion_tokens, job_stage_event.cost_usd, job_stage_event.node_path, job_stage_event.depth, job_stage_event.parent_path, job_stage_event.item_index, job_stage_event.score, job_stage_event.input_summary, job_stage_event.output_summary, job_stage_event.input_ref, job_stage_event.output_ref, job_stage_event.has_full_input, job_stage_event.has_full_output, job_stage_event.id, job_stage_event.created_at
FROM job_stage_event
WHERE job_stage_event.job_id = %(job_id_1)s::UUID""",
    "list_events[lean-after]": """execute:
SELECT job_stage_event.job_id, job_stage_event.stage, job_stage_event.status, job_stage_event.node_kind, job_stage_event.started_at, job_stage_event.finished_at, job_stage_event.detail, job_stage_event.prompt_tokens, job_stage_event.completion_tokens, job_stage_event.cost_usd, job_stage_event.node_path, job_stage_event.depth, job_stage_event.parent_path, job_stage_event.item_index, job_stage_event.score, job_stage_event.input_ref, job_stage_event.output_ref, job_stage_event.has_full_input, job_stage_event.has_full_output, job_stage_event.id, job_stage_event.created_at
FROM job_stage_event
WHERE job_stage_event.job_id = %(job_id_1)s::UUID AND job_stage_event.created_at > %(created_at_1)s::TIMESTAMP WITH TIME ZONE""",
    "list_failed_since": """execute:
SELECT job.id
FROM job
WHERE job.status = %(status_1)s AND job.finished_at > %(finished_at_1)s::TIMESTAMP WITH TIME ZONE ORDER BY job.finished_at DESC
LIMIT %(param_1)s::INTEGER""",
    "list_failed_since[collection-limit]": """execute:
SELECT job.id
FROM job
WHERE job.status = %(status_1)s AND job.finished_at > %(finished_at_1)s::TIMESTAMP WITH TIME ZONE AND job.collection_id = %(collection_id_1)s::UUID ORDER BY job.finished_at DESC
LIMIT %(param_1)s::INTEGER""",
    "list_for_collection": """execute:
SELECT job.document_id, job.collection_id, job.status, job.kind, job.cancel_requested, job.worker_id, job.attempt, job.current_stage, job.progress, job.error, job.started_at, job.finished_at, job.total_prompt_tokens, job.total_completion_tokens, job.cost_usd, job.trace_payload_bytes, job.items_done, job.items_total, job.failed_node_id, job.failed_node_kind, job.failed_item_index, job.error_type, job.replay_from, job.id, job.created_at, job.updated_at
FROM job
WHERE job.collection_id = %(collection_id_1)s::UUID ORDER BY job.created_at DESC""",
    "list_for_collection_with_names": """execute:
SELECT job.document_id, job.collection_id, job.status, job.kind, job.cancel_requested, job.worker_id, job.attempt, job.current_stage, job.progress, job.error, job.started_at, job.finished_at, job.total_prompt_tokens, job.total_completion_tokens, job.cost_usd, job.trace_payload_bytes, job.items_done, job.items_total, job.failed_node_id, job.failed_node_kind, job.failed_item_index, job.error_type, job.replay_from, job.id, job.created_at, job.updated_at, document.filename, document.title, collection.name, collection.title_field, (SELECT document_metadata.value
FROM document_metadata JOIN metadata_field ON metadata_field.id = document_metadata.field_id
WHERE document_metadata.document_id = job.document_id AND metadata_field.collection_id = job.collection_id AND metadata_field.field_name = collection.title_field AND metadata_field.scope = %(scope_1)s) AS anon_1
FROM job LEFT OUTER JOIN document ON document.id = job.document_id LEFT OUTER JOIN collection ON collection.id = job.collection_id
WHERE job.collection_id = %(collection_id_1)s::UUID ORDER BY job.created_at DESC, job.id DESC
LIMIT ALL OFFSET %(param_1)s::INTEGER""",
    "list_for_collection_with_names[page]": """execute:
SELECT job.document_id, job.collection_id, job.status, job.kind, job.cancel_requested, job.worker_id, job.attempt, job.current_stage, job.progress, job.error, job.started_at, job.finished_at, job.total_prompt_tokens, job.total_completion_tokens, job.cost_usd, job.trace_payload_bytes, job.items_done, job.items_total, job.failed_node_id, job.failed_node_kind, job.failed_item_index, job.error_type, job.replay_from, job.id, job.created_at, job.updated_at, document.filename, document.title, collection.name, collection.title_field, (SELECT document_metadata.value
FROM document_metadata JOIN metadata_field ON metadata_field.id = document_metadata.field_id
WHERE document_metadata.document_id = job.document_id AND metadata_field.collection_id = job.collection_id AND metadata_field.field_name = collection.title_field AND metadata_field.scope = %(scope_1)s) AS anon_1
FROM job LEFT OUTER JOIN document ON document.id = job.document_id LEFT OUTER JOIN collection ON collection.id = job.collection_id
WHERE job.collection_id = %(collection_id_1)s::UUID ORDER BY job.created_at DESC, job.id DESC
LIMIT %(param_1)s::INTEGER OFFSET %(param_2)s::INTEGER""",
    "list_heartbeats": """execute:
SELECT worker_heartbeats.worker_id, worker_heartbeats.worker_name, worker_heartbeats.last_seen, worker_heartbeats.started_at, worker_heartbeats.max_jobs, worker_heartbeats.cpu_percent, worker_heartbeats.mem_mb, worker_heartbeats.mem_percent
FROM worker_heartbeats ORDER BY worker_heartbeats.worker_id ASC""",
    "list_job_ids_for_collection": """execute:
SELECT job.id
FROM job
WHERE job.collection_id = %(collection_id_1)s::UUID""",
    "list_job_ids_for_document": """execute:
SELECT job.id
FROM job
WHERE job.document_id = %(document_id_1)s::UUID""",
    "list_job_ids_for_documents": """execute:
SELECT job.id
FROM job
WHERE job.document_id IN (__[POSTCOMPILE_document_id_1])""",
    "list_over_job_timeout": """execute:
SELECT job.document_id, job.collection_id, job.status, job.kind, job.cancel_requested, job.worker_id, job.attempt, job.current_stage, job.progress, job.error, job.started_at, job.finished_at, job.total_prompt_tokens, job.total_completion_tokens, job.cost_usd, job.trace_payload_bytes, job.items_done, job.items_total, job.failed_node_id, job.failed_node_kind, job.failed_item_index, job.error_type, job.replay_from, job.id, job.created_at, job.updated_at, coalesce(collection.job_timeout_seconds, %(coalesce_2)s) AS coalesce_1
FROM job JOIN collection ON collection.id = job.collection_id JOIN worker_heartbeats ON worker_heartbeats.worker_id = job.worker_id
WHERE job.status = %(status_1)s AND job.started_at IS NOT NULL AND job.started_at < now() - make_interval(%(make_interval_1)s::INTEGER, %(make_interval_2)s::INTEGER, %(make_interval_3)s::INTEGER, %(make_interval_4)s::INTEGER, %(make_interval_5)s::INTEGER, %(make_interval_6)s::INTEGER, coalesce(collection.job_timeout_seconds, %(coalesce_2)s) + %(coalesce_3)s) AND worker_heartbeats.last_seen >= now() - make_interval(%(make_interval_7)s::INTEGER, %(make_interval_8)s::INTEGER, %(make_interval_9)s::INTEGER, %(make_interval_10)s::INTEGER, %(make_interval_11)s::INTEGER, %(make_interval_12)s::INTEGER, %(make_interval_13)s) ORDER BY job.started_at ASC""",
    "list_over_job_timeout[rebuild-timeout]": """execute:
SELECT job.document_id, job.collection_id, job.status, job.kind, job.cancel_requested, job.worker_id, job.attempt, job.current_stage, job.progress, job.error, job.started_at, job.finished_at, job.total_prompt_tokens, job.total_completion_tokens, job.cost_usd, job.trace_payload_bytes, job.items_done, job.items_total, job.failed_node_id, job.failed_node_kind, job.failed_item_index, job.error_type, job.replay_from, job.id, job.created_at, job.updated_at, CASE WHEN (job.kind = %(kind_1)s) THEN %(param_1)s ELSE coalesce(collection.job_timeout_seconds, %(coalesce_1)s) END AS anon_1
FROM job JOIN collection ON collection.id = job.collection_id JOIN worker_heartbeats ON worker_heartbeats.worker_id = job.worker_id
WHERE job.status = %(status_1)s AND job.started_at IS NOT NULL AND job.started_at < now() - make_interval(%(make_interval_1)s::INTEGER, %(make_interval_2)s::INTEGER, %(make_interval_3)s::INTEGER, %(make_interval_4)s::INTEGER, %(make_interval_5)s::INTEGER, %(make_interval_6)s::INTEGER, CASE WHEN (job.kind = %(kind_1)s) THEN %(param_1)s ELSE coalesce(collection.job_timeout_seconds, %(coalesce_1)s) END + %(param_2)s) AND worker_heartbeats.last_seen >= now() - make_interval(%(make_interval_7)s::INTEGER, %(make_interval_8)s::INTEGER, %(make_interval_9)s::INTEGER, %(make_interval_10)s::INTEGER, %(make_interval_11)s::INTEGER, %(make_interval_12)s::INTEGER, %(make_interval_13)s) ORDER BY job.started_at ASC""",
    "list_running_for_worker": """execute:
SELECT job.document_id, job.collection_id, job.status, job.kind, job.cancel_requested, job.worker_id, job.attempt, job.current_stage, job.progress, job.error, job.started_at, job.finished_at, job.total_prompt_tokens, job.total_completion_tokens, job.cost_usd, job.trace_payload_bytes, job.items_done, job.items_total, job.failed_node_id, job.failed_node_kind, job.failed_item_index, job.error_type, job.replay_from, job.id, job.created_at, job.updated_at
FROM job
WHERE job.status = %(status_1)s AND job.worker_id = %(worker_id_1)s::VARCHAR""",
    "list_stale": """execute:
SELECT job.document_id, job.collection_id, job.status, job.kind, job.cancel_requested, job.worker_id, job.attempt, job.current_stage, job.progress, job.error, job.started_at, job.finished_at, job.total_prompt_tokens, job.total_completion_tokens, job.cost_usd, job.trace_payload_bytes, job.items_done, job.items_total, job.failed_node_id, job.failed_node_kind, job.failed_item_index, job.error_type, job.replay_from, job.id, job.created_at, job.updated_at
FROM job LEFT OUTER JOIN worker_heartbeats ON worker_heartbeats.worker_id = job.worker_id
WHERE job.status = %(status_1)s AND job.updated_at < now() - %(now_1)s AND (worker_heartbeats.worker_id IS NULL OR worker_heartbeats.last_seen < now() - %(now_2)s) ORDER BY job.updated_at ASC""",
    "list_terminal_job_ids_for_collection": """execute:
SELECT job.id
FROM job
WHERE job.collection_id = %(collection_id_1)s::UUID AND job.status IN (__[POSTCOMPILE_status_1])""",
    "list_terminal_job_ids_for_document": """execute:
SELECT job.id
FROM job
WHERE job.document_id = %(document_id_1)s::UUID AND job.status IN (__[POSTCOMPILE_status_1])""",
    "list_trace_job_ids_before": """execute:
SELECT job.id
FROM job JOIN job_stage_event ON job_stage_event.job_id = job.id
WHERE job.created_at < %(created_at_1)s::TIMESTAMP WITH TIME ZONE AND (job_stage_event.has_full_input IS true OR job_stage_event.has_full_output IS true) GROUP BY job.id, job.created_at ORDER BY job.created_at ASC
LIMIT %(param_1)s::INTEGER""",
    "list_with_names": """execute:
SELECT job.document_id, job.collection_id, job.status, job.kind, job.cancel_requested, job.worker_id, job.attempt, job.current_stage, job.progress, job.error, job.started_at, job.finished_at, job.total_prompt_tokens, job.total_completion_tokens, job.cost_usd, job.trace_payload_bytes, job.items_done, job.items_total, job.failed_node_id, job.failed_node_kind, job.failed_item_index, job.error_type, job.replay_from, job.id, job.created_at, job.updated_at, document.filename, document.title, collection.name, collection.title_field, (SELECT document_metadata.value
FROM document_metadata JOIN metadata_field ON metadata_field.id = document_metadata.field_id
WHERE document_metadata.document_id = job.document_id AND metadata_field.collection_id = job.collection_id AND metadata_field.field_name = collection.title_field AND metadata_field.scope = %(scope_1)s) AS anon_1
FROM job LEFT OUTER JOIN document ON document.id = job.document_id LEFT OUTER JOIN collection ON collection.id = job.collection_id ORDER BY job.created_at DESC, job.id DESC
LIMIT ALL OFFSET %(param_1)s::INTEGER""",
    "list_with_names[all-filters-page]": """execute:
SELECT job.document_id, job.collection_id, job.status, job.kind, job.cancel_requested, job.worker_id, job.attempt, job.current_stage, job.progress, job.error, job.started_at, job.finished_at, job.total_prompt_tokens, job.total_completion_tokens, job.cost_usd, job.trace_payload_bytes, job.items_done, job.items_total, job.failed_node_id, job.failed_node_kind, job.failed_item_index, job.error_type, job.replay_from, job.id, job.created_at, job.updated_at, document.filename, document.title, collection.name, collection.title_field, (SELECT document_metadata.value
FROM document_metadata JOIN metadata_field ON metadata_field.id = document_metadata.field_id
WHERE document_metadata.document_id = job.document_id AND metadata_field.collection_id = job.collection_id AND metadata_field.field_name = collection.title_field AND metadata_field.scope = %(scope_1)s) AS anon_1
FROM job LEFT OUTER JOIN document ON document.id = job.document_id LEFT OUTER JOIN collection ON collection.id = job.collection_id
WHERE job.collection_id = %(collection_id_1)s::UUID AND job.status IN (__[POSTCOMPILE_status_1]) AND job.current_stage = %(current_stage_1)s::VARCHAR AND job.error_type = %(error_type_1)s::VARCHAR AND job.created_at >= %(created_at_1)s::TIMESTAMP WITH TIME ZONE AND job.created_at <= %(created_at_2)s::TIMESTAMP WITH TIME ZONE AND (CAST(job.id AS VARCHAR) ILIKE %(param_1)s::VARCHAR OR CAST(job.document_id AS VARCHAR) ILIKE %(param_2)s::VARCHAR) ORDER BY job.status DESC, job.id DESC
LIMIT %(param_3)s::INTEGER OFFSET %(param_4)s::INTEGER""",
    "list_with_names[oldest-first]": """execute:
SELECT job.document_id, job.collection_id, job.status, job.kind, job.cancel_requested, job.worker_id, job.attempt, job.current_stage, job.progress, job.error, job.started_at, job.finished_at, job.total_prompt_tokens, job.total_completion_tokens, job.cost_usd, job.trace_payload_bytes, job.items_done, job.items_total, job.failed_node_id, job.failed_node_kind, job.failed_item_index, job.error_type, job.replay_from, job.id, job.created_at, job.updated_at, document.filename, document.title, collection.name, collection.title_field, (SELECT document_metadata.value
FROM document_metadata JOIN metadata_field ON metadata_field.id = document_metadata.field_id
WHERE document_metadata.document_id = job.document_id AND metadata_field.collection_id = job.collection_id AND metadata_field.field_name = collection.title_field AND metadata_field.scope = %(scope_1)s) AS anon_1
FROM job LEFT OUTER JOIN document ON document.id = job.document_id LEFT OUTER JOIN collection ON collection.id = job.collection_id
WHERE job.collection_id = %(collection_id_1)s::UUID ORDER BY job.created_at ASC, job.id ASC
LIMIT ALL OFFSET %(param_1)s::INTEGER""",
    "mark_done": """execute:
UPDATE job SET status=%(status)s, progress=%(progress)s::SMALLINT, finished_at=%(finished_at)s::TIMESTAMP WITH TIME ZONE, updated_at=now() WHERE job.id = %(id_1)s::UUID AND job.status = %(status_1)s""",
    "mark_failed": """execute:
UPDATE job SET status=%(status)s, error=%(error)s::VARCHAR, finished_at=%(finished_at)s::TIMESTAMP WITH TIME ZONE, failed_node_id=%(failed_node_id)s::VARCHAR, failed_node_kind=%(failed_node_kind)s::VARCHAR, failed_item_index=%(failed_item_index)s::SMALLINT, error_type=%(error_type)s::VARCHAR, updated_at=now() WHERE job.id = %(id_1)s::UUID AND job.status = %(status_1)s
--
execute:
UPDATE job_stage_event SET status=%(status)s::VARCHAR, finished_at=%(finished_at)s::TIMESTAMP WITH TIME ZONE, detail=%(detail)s::VARCHAR WHERE job_stage_event.job_id = %(job_id_1)s::UUID AND job_stage_event.finished_at IS NULL""",
    "mark_failed[attributed]": """execute:
UPDATE job SET status=%(status)s, error=%(error)s::VARCHAR, finished_at=%(finished_at)s::TIMESTAMP WITH TIME ZONE, failed_node_id=%(failed_node_id)s::VARCHAR, failed_node_kind=%(failed_node_kind)s::VARCHAR, failed_item_index=%(failed_item_index)s::SMALLINT, error_type=%(error_type)s::VARCHAR, updated_at=now() WHERE job.id = %(id_1)s::UUID AND job.status = %(status_1)s
--
execute:
UPDATE job_stage_event SET status=%(status)s::VARCHAR, finished_at=%(finished_at)s::TIMESTAMP WITH TIME ZONE, detail=%(detail)s::VARCHAR WHERE job_stage_event.job_id = %(job_id_1)s::UUID AND job_stage_event.finished_at IS NULL""",
    "mark_running": """get:Job
--
set:Job.status=<JobStatus.RUNNING: 'running'>
--
set:Job.worker_id='worker-1'
--
set:Job.attempt=2
--
set:Job.started_at=datetime.datetime(2026, 1, 2, 3, 4, 5)
--
set:Job.error=None
--
set:Job.finished_at=None
--
set:Job.current_stage=None
--
set:Job.progress=0
--
set:Job.cancel_requested=False
--
set:Job.failed_node_id=None
--
set:Job.failed_node_kind=None
--
set:Job.failed_item_index=None
--
set:Job.error_type=None
--
set:Job.items_done=None
--
set:Job.items_total=None""",
    "mark_running[terminal-job-untouched]": """get:Job""",
    "mark_terminal": """execute:
UPDATE job SET status=%(status)s, cancel_requested=%(cancel_requested)s, error=%(error)s::VARCHAR, finished_at=%(finished_at)s::TIMESTAMP WITH TIME ZONE, updated_at=now() WHERE job.id = %(id_1)s::UUID AND job.status IN (__[POSTCOMPILE_status_1]) RETURNING job.document_id, job.collection_id, job.status, job.kind, job.cancel_requested, job.worker_id, job.attempt, job.current_stage, job.progress, job.error, job.started_at, job.finished_at, job.total_prompt_tokens, job.total_completion_tokens, job.cost_usd, job.trace_payload_bytes, job.items_done, job.items_total, job.failed_node_id, job.failed_node_kind, job.failed_item_index, job.error_type, job.replay_from, job.id, job.created_at, job.updated_at
--
execute:
UPDATE job_stage_event SET status=%(status)s::VARCHAR, finished_at=%(finished_at)s::TIMESTAMP WITH TIME ZONE, detail=%(detail)s::VARCHAR WHERE job_stage_event.job_id = %(job_id_1)s::UUID AND job_stage_event.finished_at IS NULL""",
    "mark_terminal[attributed]": """execute:
UPDATE job SET status=%(status)s, cancel_requested=%(cancel_requested)s, error=%(error)s::VARCHAR, finished_at=%(finished_at)s::TIMESTAMP WITH TIME ZONE, error_type=%(error_type)s::VARCHAR, updated_at=now() WHERE job.id = %(id_1)s::UUID AND job.status IN (__[POSTCOMPILE_status_1]) RETURNING job.document_id, job.collection_id, job.status, job.kind, job.cancel_requested, job.worker_id, job.attempt, job.current_stage, job.progress, job.error, job.started_at, job.finished_at, job.total_prompt_tokens, job.total_completion_tokens, job.cost_usd, job.trace_payload_bytes, job.items_done, job.items_total, job.failed_node_id, job.failed_node_kind, job.failed_item_index, job.error_type, job.replay_from, job.id, job.created_at, job.updated_at
--
execute:
UPDATE job_stage_event SET status=%(status)s::VARCHAR, finished_at=%(finished_at)s::TIMESTAMP WITH TIME ZONE, detail=%(detail)s::VARCHAR WHERE job_stage_event.job_id = %(job_id_1)s::UUID AND job_stage_event.finished_at IS NULL""",
    "prune_history": """execute:
DELETE FROM job WHERE job.status IN (__[POSTCOMPILE_status_1]) AND job.created_at < %(created_at_1)s::TIMESTAMP WITH TIME ZONE AND NOT (EXISTS (SELECT job_stage_event.id
FROM job_stage_event
WHERE job_stage_event.job_id = job.id AND (job_stage_event.has_full_input IS true OR job_stage_event.has_full_output IS true)))""",
    "prune_stale_heartbeats": """execute:
DELETE FROM worker_heartbeats WHERE worker_heartbeats.last_seen < now() - %(now_1)s RETURNING worker_heartbeats.worker_id""",
    "queue_depth": """execute:
SELECT job.status, count(job.id) AS count_1
FROM job
WHERE job.status IN (__[POSTCOMPILE_status_1]) GROUP BY job.status""",
    "queue_depth[collection]": """execute:
SELECT job.status, count(job.id) AS count_1
FROM job
WHERE job.status IN (__[POSTCOMPILE_status_1]) AND job.collection_id = %(collection_id_1)s::UUID GROUP BY job.status""",
    "record_event": """add:JobStageEvent
--
flush""",
    "request_cancel": """get:Job
--
set:Job.cancel_requested=True""",
    "set_items": """get:Job
--
set:Job.items_done=3
--
set:Job.items_total=10""",
    "set_items[unknown-total]": """get:Job
--
set:Job.items_done=3
--
set:Job.items_total=None""",
    "set_progress": """get:Job
--
set:Job.current_stage='parse'
--
set:Job.progress=40""",
    "set_trace_payload_bytes": """execute:
UPDATE job SET trace_payload_bytes=%(trace_payload_bytes)s::BIGINT, updated_at=now() WHERE job.id = %(id_1)s::UUID""",
    "status_counts": """execute:
SELECT job.status, count(job.id) AS count_1
FROM job GROUP BY job.status""",
    "upsert_heartbeat": """execute:
INSERT INTO worker_heartbeats (worker_id, worker_name, last_seen, started_at, max_jobs, cpu_percent, mem_mb, mem_percent) VALUES (%(worker_id)s::VARCHAR, %(worker_name)s::VARCHAR, %(last_seen)s::TIMESTAMP WITH TIME ZONE, %(started_at)s::TIMESTAMP WITH TIME ZONE, %(max_jobs)s::INTEGER, %(cpu_percent)s, %(mem_mb)s, %(mem_percent)s) ON CONFLICT (worker_id) DO UPDATE SET worker_name = %(param_1)s::VARCHAR, last_seen = %(param_2)s::TIMESTAMP WITH TIME ZONE, started_at = %(param_3)s::TIMESTAMP WITH TIME ZONE, max_jobs = %(param_4)s::INTEGER, cpu_percent = %(param_5)s, mem_mb = %(param_6)s, mem_percent = %(param_7)s""",
    "upsert_heartbeat[with-metrics]": """execute:
INSERT INTO worker_heartbeats (worker_id, worker_name, last_seen, started_at, max_jobs, cpu_percent, mem_mb, mem_percent) VALUES (%(worker_id)s::VARCHAR, %(worker_name)s::VARCHAR, %(last_seen)s::TIMESTAMP WITH TIME ZONE, %(started_at)s::TIMESTAMP WITH TIME ZONE, %(max_jobs)s::INTEGER, %(cpu_percent)s, %(mem_mb)s, %(mem_percent)s) ON CONFLICT (worker_id) DO UPDATE SET worker_name = %(param_1)s::VARCHAR, last_seen = %(param_2)s::TIMESTAMP WITH TIME ZONE, started_at = %(param_3)s::TIMESTAMP WITH TIME ZONE, max_jobs = %(param_4)s::INTEGER, cpu_percent = %(param_5)s, mem_mb = %(param_6)s, mem_percent = %(param_7)s""",
}
