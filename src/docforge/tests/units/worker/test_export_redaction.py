"""Collection EXPORT: provider-secret redaction in the bundle contract.

A `.dcexport` bundle is portable and downloadable by any READ-scoped key, so it must NEVER carry a
live provider ``api_key``. This pins that ``CollectionExporter._contract`` runs the SAME masking the
API's collection GET applies over the live ``pipeline`` + ``search`` blobs AND every archived
``config_versions[].config`` snapshot — so ``collection.json`` contains no real secret, only masks.

``collection_transfer`` is flat-importable (worker/backend/libs is on sys.path — see the root
conftest); the exporter touches no ``backend.context``, so it imports without the worker CONTEXT shim.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from collection_transfer.export.exporter import CollectionExporter

VLM_KEY = "sk-proj-VLMSECRETLEAK1234"
OCR_KEY = "mistral-OCRSECRETKEY-xyz9"
RERANK_KEY = "sk-RERANKSECRET-qwer"
HISTORIC_KEY = "sk-HISTORICSECRET-8888"


def _leaky_pipeline() -> dict:
    """A pipeline blob with real provider keys across a top node, a nested group and a foreach body."""
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


def _historic_config() -> dict:
    """An archived config snapshot — its provider key must be redacted too (history leaks as well).

    A config_version stores the PRODUCTION wrapper shape ``{"pipeline": blob, "search": blob}`` (see
    CollectionsFacade.add_config_version), NOT a raw node blob — the secret is nested one level deeper.
    """
    return {
        "pipeline": {
            "node_type": "group",
            "id": "old",
            "nodes": [
                {
                    "node_type": "action",
                    "id": "vlm_old",
                    "family": "vlm",
                    "kind": "openai_compatible",
                    "config": {"api_key": HISTORIC_KEY},
                }
            ],
        },
        "search": {"node_type": "group", "id": "sold", "nodes": []},
    }


def _facade() -> SimpleNamespace:
    """A CollectionTransferFacade stand-in returning one archived config version."""
    version = SimpleNamespace(version=1, config=_historic_config(), note="v1", created_at=None)
    return SimpleNamespace(list_config_versions=AsyncMock(return_value=[version]))


def _collection() -> SimpleNamespace:
    return SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        name="c1",
        supported_formats=["pdf"],
        max_file_size_bytes=1_000_000,
        job_timeout_seconds=None,
        needs_reindex=False,
        pipeline=_leaky_pipeline(),
        search=_leaky_search(),
    )


async def test_export_contract_redacts_every_provider_secret() -> None:
    exporter = CollectionExporter(_facade(), docforge_version="test", created_at="now")

    contract = await exporter._contract(_collection())

    # No real key survives anywhere in the serialized contract — pipeline, search or history.
    dumped = contract.model_dump_json()
    for secret in (VLM_KEY, OCR_KEY, RERANK_KEY, HISTORIC_KEY):
        assert secret not in dumped
    # And the masks ARE present (an operator still sees a key WAS set, and must re-enter it on import).
    assert contract.pipeline["nodes"][0]["config"]["api_key"] == "__redacted__1234"
    assert contract.pipeline["nodes"][1]["nodes"][0]["config"]["api_key"] == "__redacted__xyz9"
    assert contract.search["nodes"][0]["config"]["api_key"] == "__redacted__qwer"
    historic = contract.config_versions[0].config["pipeline"]["nodes"][0]["config"]["api_key"]
    assert historic == "__redacted__8888"


async def test_export_contract_does_not_mutate_the_stored_blob() -> None:
    """Redaction copies — the ORM-loaded collection blob keeps its real key (ingestion reads it)."""
    collection = _collection()
    exporter = CollectionExporter(_facade(), docforge_version="test", created_at="now")

    await exporter._contract(collection)

    assert collection.pipeline["nodes"][0]["config"]["api_key"] == VLM_KEY
    assert collection.search["nodes"][0]["config"]["api_key"] == RERANK_KEY
