---
name: backend-endpoint-map
description: REST path/verb/body facts the docforge_mcp SDK must match, derived from backend/app.py + routers
metadata:
  type: reference
---

Path assembly lives in `src/docforge/backend/app.py`:
- V1 = `/api/v1`; COL = `/api/v1/collections`; DOC = `COL/{collection_id}/documents`
- config router prefix = `COL/{collection_id}/config`
- files router prefix = `DOC/{document_id}`; chunks = `DOC/{document_id}/chunks`; pages = `DOC/{document_id}/pages`
- jobs = `V1/jobs`; monitoring = `V1/monitoring` (both top-level, NOT collection-scoped)

Leaf paths + verbs the SDK is validated against (all confirmed matching as of P8 review):
- health: GET `/health/ping`
- discovery: GET `/discovery?collection_id=`
- collections: GET `/list`, POST `/create` (body `{name, ...optional}`), DELETE `/{id}/delete`
- config: GET `/state` `/schema` `/history`; POST `/update` (body `{patch, note}`), POST `/rollback` (body `{version}`)
- documents: POST `/ingest` (multipart: file field `file` + form field `metadata` = JSON string),
  GET `/list`, GET `/{id}`, POST `/{id}/update` (body `{metadata, reindex}`),
  POST `/{id}/reingest` (body `{force}`), DELETE `/{id}/delete`
- search: POST `/search` and POST `/{document_id}/search`; body = SearchRequest `{query, top_k, filters?, weights?, debug}`
- files: GET `/original` `/markdown` `/pdf` `/figures/{block_id:path}` (server uses `:path` converter;
  client sends literal slashes un-encoded — correct)
- chunks: GET `/list`, GET `/{chunk_id}`, POST `/{chunk_id}/update` (body `{raw_text, embed_text, reindex}`,
  >=1 of raw_text/embed_text required — enforced server-side with 422)
- pages: GET `/list`, GET `/{page_number}`, GET `/{page_number}/screenshot` (returns image/png bytes →
  MCP tool wraps in `Image(data=..., format="png")`), POST `/{page_number}/reingest`
- jobs: GET `` (empty leaf, i.e. `/api/v1/jobs`), GET `/{job_id}`, POST `/{job_id}/cancel`
- monitoring: GET `/queue` `/workers` `/overview` `/discovery`

IMPORTANT: there is NO collection-level reindex endpoint anymore. P5's `POST /collections/.../reindex`
+ `GET /schema` + `PUT /pipeline` were superseded — reindex is now driven by config changes
(per-collection `needs_reindex` flag) and per-document `reingest`. The SDK correctly omits a reindex tool.
36-tool count = health 1 + discovery 1 + collections 3 + config 5 + documents 6 + search 2 + files 4 +
chunks 3 + pages 4 + jobs 3 + monitoring 4.
