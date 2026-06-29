---
name: metagen-live-test
description: Design decisions for the S5b metagen live test — cost-bounded opt-in pattern, where to read back generated values, class-scope fixture for 1 LLM call
metadata:
  type: project
---

## File: `tests/live_test/test_metagen_live.py`

### Opt-in pattern
`pytestmark = pytest.mark.skipif(not (_LLM_URL and _LLM_MODEL), reason=...)` at module level.
This is superior to a fixture-level skip for opt-in cost gates: the tests collect normally
(`--collect-only` shows them), no fixtures fire when the condition is false, and the skip
reason message is clear about which env vars to set.

**Required env vars (all four read at module import):**
- `DOCFORGE_TEST_METAGEN_LLM_URL` — LLM base_url (e.g. `https://api.openai.com/v1`)
- `DOCFORGE_TEST_METAGEN_LLM_MODEL` — model name (e.g. `gpt-4o-mini`)
- `DOCFORGE_TEST_METAGEN_LLM_KEY` — api_key (optional; defaults to `"local"`)
- `DOCFORGE_TEST_METAGEN_LLM_LOCALITY` — `"local"` or `"external"` (defaults to `"external"`)

### Cost bounding: class-scoped fixture = 1 LLM call
`scope="class"` on the `metagen_context` fixture means the fixture runs ONCE for the
`TestMetagenDocumentScope` class even though there are two test methods. Class-scoped
fixtures can use session-scoped fixtures (`live_client`, `corpus`); they cannot use
function-scoped ones (so no `make_collection`).

For the teardown, the fixture directly calls `live_client.delete(f"/collections/{cid}/delete")`
rather than relying on `make_collection`'s teardown.

### Where doc-scope generated fields live
**Critical finding:** doc-scope generated values from S5b (`doc_fields`) are merged into
`doc_meta` in `S456Runner._run_s6_and_flush_traces()`. This `doc_meta` is passed to S6 which
writes it to the Qdrant payload of EVERY chunk via `S6IndexHelpers.build_payload()`.

They are NOT written back to `DocumentModel.implicit_meta` (Postgres column). The embed-chain
traces ARE written back to `implicit_meta`, but not the generated metadata values.

**Consequence:** to read back a generated field, use Qdrant scroll, NOT the document API.
The `DocumentResponse` model has no `doc_meta` / `generated_meta` field.

### Reading from Qdrant
```python
def _qdrant_scroll_payload(collection_id: str, doc_id: str) -> dict[str, Any]:
    resp = httpx.post(
        f"{QDRANT_URL}/collections/{collection_id}/points/scroll",
        json={"filter": {"must": [{"key": "document_id", "match": {"value": doc_id}}]},
              "with_payload": True, "limit": 1},
        timeout=15.0,
    )
    if resp.status_code != 200:
        return {}
    points = resp.json().get("result", {}).get("points", [])
    return points[0].get("payload", {}) if points else {}
```

`doc_id` must be a plain string (from `str(ing["doc_id"])`). The `document_id` key in the
Qdrant payload is stored as a string because `Chunk.document_id: str`.

### Graceful degrade contract
`MetaGenConfig.gate` defaults to `failure_policy="continue"`. When the LLM call fails or
returns empty, S5b does NOT fail the document — it degrades silently. The test therefore:
1. Always asserts `document.get("status") == "done"` (hard fail if error)
2. Only asserts the generated value is non-empty when it IS present
3. Emits `warnings.warn(...)` (UserWarning) if the field is missing/empty — no hard failure
4. The filterability test calls `pytest.skip()` when the value is missing (no false failures)

### Corpus doc choice
`report_en_html` (key from `_html("en", "report_en.html")`): no Gotenberg conversion,
Docling parses HTML natively, min_chunks=8, fast. Fallback: `corpus.by_format("html")`.
The collection uses `supported_formats=["html"]`.

### Pipeline config shape
```python
pipeline = {
    "embed": {"chain": [{"id": "bge_server", "base_url": "http://bge_server:80", "embed_sparse": False}]},
    "metagen": {
        "chain": [{"id": "openai_compat", "base_url": "...", "api_key": "...",
                   "model": "...", "locality": "external"}],
        "targets": [{"field": "doc_summary", "prompt": "...", "scope": "document"}],
    }
}
```

### Metadata schema shape for generated field
```python
{"field_name": "doc_summary", "field_type": "string", "origin": "generated",
 "required": False, "filterable": True, "lexical": False, "semantic": False}
```
`origin="generated"` is mandatory — without it the field is not exempt from
upload-time required/unknown-field validation (AdmissionValidator).
Valid `field_type` values: `string`, `number`, `date`, `bool`, `enum`, `string[]`
(NOT `keyword_list` or `boolean`).

### Search endpoint (verified)
`POST /collections/{cid}/documents/search` (confirmed in `test_search_live.py`).

**Why:** `field_index/helpers.py resolve_field_text` reads from `chunk.derived_meta` (chunk scope)
then `doc_meta` (doc scope) when building payloads — so a filterable doc-scope field IS
present in every chunk's Qdrant payload and IS usable as a search filter.
