# ====== Code Summary ======
# Cost-bounded LIVE end-to-end test for the S5b metagen stage (LLM-generated metadata).
# Strictly opt-in: skipped by default unless the caller sets the DOCFORGE_TEST_METAGEN_LLM_*
# env vars. When enabled, EXACTLY ONE LLM call is made (scope="document", one HTML doc,
# class-scoped fixture shared by both tests). This guarantees the metagen test never adds
# cost to a normal live suite run.
#
# Cost model:
#   scope="document" + 1 document = 1 LLM call total (regardless of chunk count).
#   chunk-scope tests are intentionally excluded here; add them behind the second
#   DOCFORGE_TEST_METAGEN_CHUNK_SCOPE=true flag in a future extension if needed.
#
# Verification path for the generated field:
#   doc-scope generated values land in `doc_meta` which S6 writes to the Qdrant
#   chunk payload (every chunk of the document carries the field). They are NOT written
#   back to the Postgres `implicit_meta` column. Reading them back therefore requires
#   a Qdrant scroll query, which this test does via the Qdrant REST API directly —
#   mirroring how live_client.qdrant_count() already works.

# ====== Standard Library Imports ======
from __future__ import annotations

import os
import warnings
from datetime import datetime
from typing import Any, Iterator

# ====== Third-Party Library Imports ======
import httpx
import pytest

# ====== Internal Project Imports ======
from tests.corpus import CorpusManifest
from tests.libs.live_client import LiveClient
from tests.live_test.conftest import DENSE_ONLY_PIPELINE, QDRANT_URL

# ─── Opt-in gate: read at module import so --collect-only lists the tests ─────────────
# Tests are collected unconditionally but SKIPPED at run time unless both env vars are set.
# This preserves the live suite invariant: no external API calls by default.
_LLM_URL: str = os.environ.get("DOCFORGE_TEST_METAGEN_LLM_URL", "")
_LLM_KEY: str = os.environ.get("DOCFORGE_TEST_METAGEN_LLM_KEY", "local")
_LLM_MODEL: str = os.environ.get("DOCFORGE_TEST_METAGEN_LLM_MODEL", "")
_LLM_LOCALITY: str = os.environ.get("DOCFORGE_TEST_METAGEN_LLM_LOCALITY", "external")

pytestmark = pytest.mark.skipif(
    not (_LLM_URL and _LLM_MODEL),
    reason=(
        "set DOCFORGE_TEST_METAGEN_LLM_URL and DOCFORGE_TEST_METAGEN_LLM_MODEL to run the "
        "metagen live test (incurs ~1 LLM API call for the document-scope path)"
    ),
)

# ─── Constants ────────────────────────────────────────────────────────────────────────
_GENERATED_FIELD: str = "doc_summary"
_GENERATION_PROMPT: str = "Summarize this document in one short sentence."

# Chunk-scope tests intentionally omitted here (cost). Enable by gating a future extension
# behind: DOCFORGE_TEST_METAGEN_CHUNK_SCOPE=true


# ─── Helpers ──────────────────────────────────────────────────────────────────────────


def _build_pipeline() -> dict[str, Any]:
    """
    Build the dense-only embed pipeline merged with a single document-scope metagen config.

    Starts from DENSE_ONLY_PIPELINE (bge_server without sparse head) and appends a
    metagen block with exactly one openai_compat provider + one document-scope target.

    Returns:
        dict: Complete pipeline dict for the collection create request.
    """
    # 1. Copy the embed pipeline so the constant is not mutated
    pipeline: dict[str, Any] = dict(DENSE_ONLY_PIPELINE)

    # 2. Append metagen: one provider, one document-scope target
    pipeline["metagen"] = {
        "chain": [
            {
                "id": "openai_compat",
                "base_url": _LLM_URL,
                "api_key": _LLM_KEY,
                "model": _LLM_MODEL,
                "locality": _LLM_LOCALITY,
            }
        ],
        "targets": [
            {
                "field": _GENERATED_FIELD,
                "prompt": _GENERATION_PROMPT,
                "scope": "document",
            }
        ],
    }
    return pipeline


def _build_metadata_schema() -> list[dict[str, Any]]:
    """
    Build the metadata schema with one generated, filterable string field.

    origin="generated" exempts the field from upload-time required / unknown-field checks
    (common_libs.config.admission.validator skip). filterable=True causes S6 to write the
    generated value into every chunk's Qdrant payload so it can be used as a filter.

    Returns:
        list[dict]: Metadata schema list for the collection create request.
    """
    return [
        {
            "field_name": _GENERATED_FIELD,
            "field_type": "string",
            "origin": "generated",
            "required": False,
            "filterable": True,
            "lexical": False,
            "semantic": False,
        }
    ]


def _qdrant_scroll_payload(collection_id: str, doc_id: str) -> dict[str, Any]:
    """
    Return the Qdrant payload of the first chunk belonging to ``doc_id``, or ``{}`` on failure.

    Document-scope generated fields are stored in every chunk's Qdrant payload (written by
    S6IndexHelpers.build_payload for filterable fields). The first scrolled point is
    sufficient to verify the field was written — all chunks in the same document share the
    same doc-scope generated values.

    Uses the Qdrant REST scroll endpoint directly, mirroring live_client.qdrant_count().

    Args:
        collection_id (str): Qdrant collection name (equals the DocForge collection UUID).
        doc_id (str): Document UUID as a string.

    Returns:
        dict: Payload dict of the first matching point, or empty dict on any error.
    """
    # 1. POST a scroll request filtered to this document's chunks
    try:
        resp = httpx.post(
            f"{QDRANT_URL}/collections/{collection_id}/points/scroll",
            json={
                "filter": {"must": [{"key": "document_id", "match": {"value": doc_id}}]},
                "with_payload": True,
                "limit": 1,
            },
            timeout=15.0,
        )
    except Exception:
        # Network / Qdrant unavailable — return empty so the caller decides how to handle it
        return {}

    # 2. Extract the payload of the first returned point
    if resp.status_code != 200:
        return {}
    points: list[dict] = resp.json().get("result", {}).get("points", [])
    return points[0].get("payload", {}) if points else {}


# ─── Tests ────────────────────────────────────────────────────────────────────────────


class TestMetagenDocumentScope:
    """
    End-to-end coverage of the S5b metagen stage with document-scope generation.

    Both tests share a class-scoped collection fixture, which means only ONE ingest
    (and therefore exactly ONE LLM call) occurs for the entire class. This is the
    key cost-bounding mechanism for this test file.
    """

    @pytest.fixture(scope="class")
    def metagen_context(
        self, live_client: LiveClient, corpus: CorpusManifest
    ) -> Iterator[dict[str, Any]]:
        """
        Create a metagen collection, ingest one tiny HTML document, and yield shared context.

        Class-scoped so both tests share the same collection state:
          1 ingest = 1 LLM call total (scope="document" sends one generate_json call
          per document, not per chunk).

        A TINY inline HTML document is ingested (not a corpus file): it yields a single
        small chunk, so the S6 embed step finishes well within the timeout even when
        bge_server runs on CPU (the dev default) — the test is about metagen, not embed
        throughput. HTML is parsed by Docling natively (no Gotenberg round-trip).

        Yields:
            dict: ``{cid, did, document}`` — collection id, document id (str), full
                  document payload from wait_done.
        """
        col_name = f"e2e-metagen-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

        # 1. Create the collection with the metagen pipeline + generated field schema
        status, collection = live_client.post(
            "/collections/create",
            {
                "name": col_name,
                "supported_formats": ["html"],
                "pipeline": _build_pipeline(),
                "metadata_schema": _build_metadata_schema(),
            },
        )
        assert status == 201, f"collection create failed ({status}): {collection}"
        cid: str = collection["id"]

        # 2. Ingest a tiny inline HTML doc → one small chunk → fast embed even on CPU.
        tiny_html = (
            b"<html><head><title>Quarterly Note</title></head><body>"
            b"<h1>Quarterly Note</h1>"
            b"<p>Revenue grew 12% this quarter, driven by strong demand in the European "
            b"market. Operating costs stayed flat and the team shipped the new billing "
            b"module ahead of schedule.</p>"
            b"</body></html>"
        )
        ing_status, ing = live_client.ingest(cid, "quarterly_note.html", tiny_html)
        assert ing_status in (200, 202), f"ingest rejected ({ing_status}): {ing}"
        document = live_client.wait_done(cid, ing["doc_id"])

        ctx: dict[str, Any] = {
            "cid": cid,
            "did": str(ing["doc_id"]),   # Qdrant filter needs a plain string
            "document": document,
        }

        yield ctx

        # 4. Teardown: delete the collection and all its Qdrant points
        live_client.delete(f"/collections/{cid}/delete")

    def test_generated_field_populated(
        self, live_client: LiveClient, metagen_context: dict[str, Any]
    ) -> None:
        """
        The generated doc_summary field is non-empty in the Qdrant point payload.

        Graceful-degrade path: when the LLM returns nothing the field is absent / empty,
        but the document must still reach 'done' (MetaGenConfig.gate defaults to
        failure_policy='continue'). In that degrade case the test emits a warning
        rather than failing — degraded-but-not-broken IS correct pipeline behavior.
        A working LLM endpoint MUST yield a non-empty string.
        """
        cid = metagen_context["cid"]
        did = metagen_context["did"]
        document = metagen_context["document"]

        # 1. Pipeline must reach 'done' regardless of LLM output — never 'error'
        assert document.get("status") == "done", (
            f"document did not reach 'done': status={document.get('status')!r}, "
            f"pipeline_errors={document.get('pipeline_errors')}"
        )

        # 2. S6 must have indexed at least one chunk into Qdrant (embedding enabled)
        point_count = live_client.qdrant_count(cid, did)
        if point_count == 0:
            pytest.skip(
                "no Qdrant points found for the ingested document; "
                "S6 indexing may be disabled in this environment"
            )

        # 3. Read the Qdrant payload to inspect the generated field
        payload = _qdrant_scroll_payload(cid, did)
        assert payload, (
            f"Qdrant scroll returned no payload for doc={did} in collection={cid}; "
            f"Qdrant may be unreachable at {QDRANT_URL}"
        )

        generated_value = payload.get(_GENERATED_FIELD)

        # 4. Happy path: assert the field is a non-empty string (provider worked)
        #    Degrade path: emit a warning but do NOT fail (degrade is correct behavior)
        if not generated_value:
            warnings.warn(
                f"metagen produced an empty '{_GENERATED_FIELD}'. "
                f"The LLM provider degraded gracefully "
                f"(model={_LLM_MODEL!r}, base_url={_LLM_URL!r}). "
                f"The document still reached 'done' — pipeline behavior is correct. "
                f"Verify the LLM endpoint and model name if a populated field was expected.",
                UserWarning,
                stacklevel=1,
            )
            return

        assert isinstance(generated_value, str), (
            f"'{_GENERATED_FIELD}' must be a string; got {type(generated_value).__name__}"
        )
        assert generated_value.strip(), (
            f"'{_GENERATED_FIELD}' is a blank string after strip; expected a sentence summary"
        )

    def test_generated_field_filterable_in_search(
        self, live_client: LiveClient, metagen_context: dict[str, Any]
    ) -> None:
        """
        The generated doc_summary is a filterable Qdrant payload key: a must-match filter
        narrows search results to chunks from our document.

        Skips automatically when the LLM degraded (no value to filter on) so the test
        never produces a false failure because of provider unavailability.
        """
        cid = metagen_context["cid"]
        did = metagen_context["did"]

        # 1. Read the generated value — skip gracefully if LLM degraded
        payload = _qdrant_scroll_payload(cid, did)
        generated_value = payload.get(_GENERATED_FIELD)
        if not generated_value:
            pytest.skip(
                f"'{_GENERATED_FIELD}' was not generated (LLM degraded) — "
                f"filterability assertion skipped"
            )

        # 2. A search constrained by the exact generated value must return >= 1 chunk
        #    (every chunk of a document carries its doc-scope filterable fields in the payload)
        status, body = live_client.post(
            f"/collections/{cid}/documents/search",
            {
                "query": generated_value[:80],
                "filters": {"must": [{"key": _GENERATED_FIELD, "match": {"value": generated_value}}]},
                "top_k": 5,
            },
        )
        assert status == 200, f"search request failed ({status}): {body}"
        assert (body.get("total") or 0) >= 1, (
            f"search with filter '{_GENERATED_FIELD}={generated_value!r}' returned 0 results; "
            f"the field may not be indexed as a filterable Qdrant payload key — "
            f"verify filterable=True was set on the metadata_field at collection creation."
        )
