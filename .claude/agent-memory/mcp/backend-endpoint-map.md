---
name: backend-endpoint-map
description: REST path/verb/body facts the MCP SDK (src/mcp/) must match, derived from app/backend/app.py + routers
metadata:
  type: reference
---

Path assembly lives in `src/docforge/app/backend/app.py`:
- V1 = `/api/v1`; COL = `/api/v1/collections`; DOC = `COL/{collection_id}/documents`
- config router prefix = `COL/{collection_id}/config`
- files router prefix = `DOC/{document_id}`; chunks = `DOC/{document_id}/chunks`; pages = `DOC/{document_id}/pages`
- jobs = `V1/jobs`; monitoring = `V1/monitoring` (both top-level, NOT collection-scoped)

Leaf paths + verbs the SDK is validated against (all confirmed matching as of Brique D review):
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
- limits: GET `/collections/{id}/limits`, PUT `/collections/{id}/limits` (body `{max_in_flight}`)
  — transport.put(), NOT post(). Null is sent explicitly (not omitted) to clear the cap.
  Response shape: `{collection_id, max_in_flight, in_flight}` — budget fields removed.
- monitoring: GET `/queue` `/workers` `/overview` `/discovery` `/resources`
  — `/resources` added in Brique D (device gauge + global admission limits + live load)

IMPORTANT: there is NO collection-level reindex endpoint anymore. P5's `POST /collections/.../reindex`
+ `GET /schema` + `PUT /pipeline` were superseded — reindex is now driven by config changes
(per-collection `needs_reindex` flag) and per-document `reingest`. The SDK correctly omits a reindex tool.
SSE endpoints (GET .../stream) are intentionally NOT exposed as tools — MCP has no streaming primitive.
51-tool count = health 1 + discovery 1 + auth 5 + users 4 + collections 3 + config 5 + documents 6 +
search 2 + files 4 + chunks 3 + pages 4 + jobs 3 + limits 2 + access 3 + monitoring 5.
auth: POST /auth/login, GET /auth/me, POST /auth/keys, GET /auth/keys, DELETE /auth/keys/{id}
users: POST /users, GET /users, DELETE /users/{id}, PUT /users/{id}/password
access: GET /collections/{id}/access, PUT /collections/{id}/access/{user_id}, DELETE /collections/{id}/access/{user_id}
