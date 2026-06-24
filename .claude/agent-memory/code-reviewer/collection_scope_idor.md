---
name: collection-scope-idor
description: Every {collection_id}/{document_id} route MUST check doc.collection_id == collection_id or it's a cross-collection IDOR
metadata:
  type: pattern
---

On any collection-scoped route shaped `/collections/{collection_id}/documents/{document_id}/...`, the per-collection authz dependency (`require_collection_role`) authorizes the caller against the PATH's `collection_id` only. If the handler then loads the document by `document_id` ALONE (no `doc.collection_id == collection_id` check), a user with a grant on collection A can read a document in collection B by crafting `/collections/{A}/documents/{doc_in_B}/...` — a cross-collection IDOR.

**Caught 2026-06-24** in `app/backend/routers/collections/documents/files/router.py` (`_require_done`): it returned presigned S3 URLs for any document id regardless of collection. Fixed by adding `doc.collection_id != collection_id` and threading `collection_id` into the helper + all 4 artefact call sites.

**How to apply:** for EVERY route under `{collection_id}/documents/{document_id}` (files, pages, chunks, search, get, update, reingest, delete), verify the loaded document's `collection_id` matches the path. The correct sibling pattern is in `documents/router.py::_get_document`, `pages/router.py::_require_document`, `search/router.py`. Files was the lone outlier — when reviewing new doc-scoped routes, this is the first thing to check. See [[secret-roundtrip]].
