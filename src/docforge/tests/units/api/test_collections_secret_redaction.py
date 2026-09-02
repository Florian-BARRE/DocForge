"""Collections router: PROVIDER SECRET REDACTION.

The product stores provider api_keys per collection in clear (accepted design), but must NEVER echo
them on the wire. These tests pin:
  1. the redaction helper (mask every provider api_key across nested nodes / foreach bodies / the
     search blob; leave empties; never mutate the stored blob),
  2. the write-side restore rule (a masked value PATCHed back means "keep the stored key", a real
     value overwrites, an empty clears, an orphan mask is blanked — never persisted verbatim),
  3. the end-to-end HTTP surface: neither the list nor the detail response leaks a raw key, and a
     read→PATCH round-trip of the masked blob keeps the real stored key.

`fastapi_app` puts app/ on sys.path so the `backend` imports resolve; CONTEXT.database is mocked, so
no store is touched.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

VLM_KEY = "sk-proj-VLMSECRETLEAK1234"
OCR_KEY = "mistral-OCRSECRETKEY-xyz9"
RERANK_KEY = "sk-RERANKSECRET-qwer"


def _leaky_pipeline() -> dict:
    """A hand-built pipeline blob with real provider keys, incl. a nested group + a foreach body."""
    return {
        "node_type": "group",
        "id": "root",
        "nodes": [
            {
                "node_type": "action",
                "id": "vlm1",
                "family": "vlm",
                "kind": "openai_compatible",
                "config": {"base_url": "https://api.openai.com/v1", "api_key": VLM_KEY},
            },
            {
                "node_type": "group",
                "id": "grp",
                "nodes": [
                    {
                        "node_type": "action",
                        "id": "ocr1",
                        "family": "ocr",
                        "kind": "mistral",
                        "config": {"api_key": OCR_KEY},
                    }
                ],
            },
            {
                "node_type": "foreach",
                "id": "fe",
                "item_field": "x",
                "body": {
                    "node_type": "group",
                    "id": "febody",
                    "nodes": [
                        {
                            "node_type": "action",
                            "id": "embed1",
                            "family": "embed",
                            "kind": "bge_server",
                            # empty key must stay empty (no secret, no mask)
                            "config": {"base_url": "http://bge:80", "api_key": ""},
                        }
                    ],
                },
            },
        ],
    }


def _leaky_search() -> dict:
    """A search blob carrying a reranker api_key (the search blob leaks too, not only pipeline)."""
    return {
        "node_type": "group",
        "id": "sroot",
        "nodes": [
            {
                "node_type": "action",
                "id": "rr",
                "family": "rerank",
                "kind": "cross_encoder",
                "config": {"base_url": "http://rr:80", "api_key": RERANK_KEY},
            }
        ],
    }


def _fake_collection(pipeline: dict, search: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        name="c1",
        supported_formats=["pdf"],
        max_file_size_bytes=1_000_000,
        job_timeout_seconds=None,
        needs_reindex=False,
        created_at=None,
        pipeline=pipeline,
        search=search,
    )


def _mock_db(monkeypatch, **collections_methods) -> SimpleNamespace:
    from backend.context import CONTEXT  # noqa: PLC0415

    facade = SimpleNamespace(**collections_methods)
    # The list route also reads three BATCHED fleet counters (doc / chunk / last-ingest) for the
    # health summary; stub them empty so any read path resolves without a store (redaction is the
    # concern under test here, not the counts).
    documents = SimpleNamespace(
        count_by_collections=AsyncMock(return_value={}),
        count_chunks_by_collections=AsyncMock(return_value={}),
    )
    jobs = SimpleNamespace(
        last_successful_ingest_at_by_collections=AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        CONTEXT,
        "database",
        SimpleNamespace(collections=facade, documents=documents, jobs=jobs),
    )
    return facade


# ─────────────────────────── helper: redact_blob_secrets ───────────────────────────


def test_redact_masks_every_provider_key_and_leaves_empties(fastapi_app) -> None:
    from shared_libs.pipelines.blob_secrets import MASK_PREFIX, redact_blob_secrets

    blob = _leaky_pipeline()
    masked = redact_blob_secrets(blob)

    dumped = str(masked)
    assert VLM_KEY not in dumped
    assert OCR_KEY not in dumped
    # top-level, nested-group and foreach-body nodes are all masked
    assert masked["nodes"][0]["config"]["api_key"] == f"{MASK_PREFIX}1234"
    assert masked["nodes"][1]["nodes"][0]["config"]["api_key"] == f"{MASK_PREFIX}xyz9"
    # an empty key is left empty (there is no secret to hide)
    assert masked["nodes"][2]["body"]["nodes"][0]["config"]["api_key"] == ""


def test_redact_masks_search_blob_reranker_key(fastapi_app) -> None:
    from shared_libs.pipelines.blob_secrets import MASK_PREFIX, redact_blob_secrets

    masked = redact_blob_secrets(_leaky_search())
    assert RERANK_KEY not in str(masked)
    assert masked["nodes"][0]["config"]["api_key"] == f"{MASK_PREFIX}qwer"


def test_redact_does_not_mutate_the_stored_blob(fastapi_app) -> None:
    from shared_libs.pipelines.blob_secrets import redact_blob_secrets

    blob = _leaky_pipeline()
    redact_blob_secrets(blob)
    # the ORM-loaded blob must keep its real key — ingestion/search read it later
    assert blob["nodes"][0]["config"]["api_key"] == VLM_KEY


def test_redact_passes_through_empty_and_none(fastapi_app) -> None:
    from shared_libs.pipelines.blob_secrets import redact_blob_secrets

    assert redact_blob_secrets({}) == {}
    assert redact_blob_secrets(None) is None


# ─────────────────────────── helper: restore_blob_secrets ───────────────────────────


def test_restore_keeps_stored_key_when_mask_is_sent_back(fastapi_app) -> None:
    from shared_libs.pipelines.blob_secrets import redact_blob_secrets, restore_blob_secrets

    stored = _leaky_pipeline()
    incoming = redact_blob_secrets(stored)  # the client read the mask and PATCHes it back untouched
    healed = restore_blob_secrets(incoming, stored)

    assert healed["nodes"][0]["config"]["api_key"] == VLM_KEY
    assert healed["nodes"][1]["nodes"][0]["config"]["api_key"] == OCR_KEY


def test_restore_keeps_a_genuinely_new_key(fastapi_app) -> None:
    from shared_libs.pipelines.blob_secrets import redact_blob_secrets, restore_blob_secrets

    stored = _leaky_pipeline()
    incoming = redact_blob_secrets(stored)
    incoming["nodes"][0]["config"]["api_key"] = "sk-BRANDNEW-0000"  # user typed a new key
    healed = restore_blob_secrets(incoming, stored)
    assert healed["nodes"][0]["config"]["api_key"] == "sk-BRANDNEW-0000"


def test_restore_keeps_an_intentional_clear(fastapi_app) -> None:
    from shared_libs.pipelines.blob_secrets import redact_blob_secrets, restore_blob_secrets

    stored = _leaky_pipeline()
    incoming = redact_blob_secrets(stored)
    incoming["nodes"][0]["config"]["api_key"] = ""  # user cleared the key
    healed = restore_blob_secrets(incoming, stored)
    assert healed["nodes"][0]["config"]["api_key"] == ""


def test_restore_blanks_an_orphan_mask_never_persists_it(fastapi_app) -> None:
    from shared_libs.pipelines.blob_secrets import MASK_PREFIX, restore_blob_secrets

    # a masked value on a node with no stored counterpart (unknown id) must never be stored verbatim
    incoming = {
        "nodes": [
            {
                "node_type": "action",
                "id": "ghost",
                "family": "vlm",
                "kind": "openai_compatible",
                "config": {"api_key": f"{MASK_PREFIX}dead"},
            }
        ]
    }
    healed = restore_blob_secrets(incoming, {"nodes": []})
    assert healed["nodes"][0]["config"]["api_key"] == ""


# ─────────────────────────── HTTP surface: list + detail never leak ───────────────────────────


def test_list_response_masks_every_secret(client, monkeypatch) -> None:
    fake = _fake_collection(_leaky_pipeline(), _leaky_search())
    _mock_db(
        monkeypatch,
        list_all=AsyncMock(return_value=[fake]),
        get_schema=AsyncMock(return_value=[]),
    )
    response = client.get("/api/v1/collections")
    assert response.status_code == 200, response.text
    body = response.text
    assert VLM_KEY not in body
    assert OCR_KEY not in body
    assert RERANK_KEY not in body
    assert "__redacted__" in body  # the operator still sees a key IS set


def test_detail_response_masks_every_secret(client, monkeypatch) -> None:
    fake = _fake_collection(_leaky_pipeline(), _leaky_search())
    _mock_db(
        monkeypatch,
        get=AsyncMock(return_value=fake),
        get_schema=AsyncMock(return_value=[]),
    )
    response = client.get(f"/api/v1/collections/{fake.id}")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert VLM_KEY not in response.text
    assert OCR_KEY not in response.text
    assert RERANK_KEY not in response.text
    assert payload["pipeline"]["nodes"][0]["config"]["api_key"] == "__redacted__1234"
    assert payload["search"]["nodes"][0]["config"]["api_key"] == "__redacted__qwer"


# ─────────────────────────── HTTP surface: PATCH round-trip keeps the key ───────────────────────────


def test_patch_round_trip_of_masked_pipeline_keeps_the_stored_key(client, monkeypatch) -> None:
    """A client reads a masked collection then PATCHes the blob back: the real stored key survives,
    the literal mask is NEVER written, and the response is masked again."""
    from shared_libs.pipelines.blob_secrets import redact_blob_secrets
    from shared_libs.pipelines.ingest import BlobNormalizer, IngestPipeline

    # A VALID stored pipeline (the stock default) carrying a real embed key.
    stored_blob = IngestPipeline.default_blob().model_dump(mode="json")
    for node in stored_blob["nodes"]:
        if node.get("family") == "embed":
            node["config"]["api_key"] = "sk-EMBEDSECRET-9999"
    stored_blob = BlobNormalizer.normalize(stored_blob)
    fake = _fake_collection(stored_blob, {})

    update_config = AsyncMock()
    _mock_db(
        monkeypatch,
        get=AsyncMock(return_value=fake),
        get_by_name=AsyncMock(return_value=None),
        get_schema=AsyncMock(return_value=[]),
        update_config=update_config,
    )

    # The client PATCHes back exactly what it read: the MASKED blob.
    masked_blob = redact_blob_secrets(stored_blob)
    assert "sk-EMBEDSECRET-9999" not in str(masked_blob)
    response = client.patch(f"/api/v1/collections/{fake.id}", json={"pipeline": masked_blob})
    assert response.status_code == 200, response.text

    # The persisted pipeline restored the real key — the mask was never written.
    update_config.assert_awaited_once()
    persisted = update_config.await_args.kwargs["pipeline"]
    embed = next(n for n in persisted["nodes"] if n.get("family") == "embed")
    assert embed["config"]["api_key"] == "sk-EMBEDSECRET-9999"

    # And the response the client gets back is masked again (never the raw key).
    assert "sk-EMBEDSECRET-9999" not in response.text
