# ====== Code Summary ======
# Unit tests for BgeModelsService. Covers encode_dense_sparse — the single-forward-pass path that
# returns BOTH dense and sparse vectors (the heavy embed_model is mocked, no torch / FlagEmbedding,
# so these tests assert only the post-processing contract: byte-for-byte the same dense vectors as
# encode_dense and the same sparse token lists as encode_sparse, from ONE encode() call rather than
# two) — and the BGE_LOAD_RERANKER gate (load_reranker=False skips reranker construction and the
# `reranker` property raises a gate-specific RuntimeError; thread-budget auto-derivation only
# accounts for rerank_lock contention when the reranker is actually loaded).

# ====== Standard Library Imports ======
from unittest.mock import MagicMock

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from libs.bge_models.service import BgeModelsService

# ── Fixtures ──────────────────────────────────────────────────────────────────


class _FakeVec:
    """Minimal stand-in for a numpy dense vector — supports only the ``.tolist()`` the code calls."""

    def __init__(self, data: list[float]) -> None:
        self._data = data

    def tolist(self) -> list[float]:
        return list(self._data)


def _make_service_with_mock_model() -> tuple[BgeModelsService, MagicMock]:
    """
    Build a BgeModelsService whose embed_model is a MagicMock (load() never called).

    The mock's ``encode`` returns a dict carrying BOTH ``dense_vecs`` and ``lexical_weights``, as
    the real BGEM3FlagModel does when both heads are requested.

    Returns:
        tuple[BgeModelsService, MagicMock]: The service and its injected embed_model mock.
    """
    service = BgeModelsService(
        embed_model_id="stub-embed",
        rerank_model_id="stub-rerank",
        device_policy="cpu",
        fp16_requested=False,
    )
    mock_model = MagicMock()
    mock_model.encode.return_value = {
        "dense_vecs": [_FakeVec([1.0, 2.0, 3.0]), _FakeVec([4.0, 5.0, 6.0])],
        "lexical_weights": [{"5": 0.5, "9": 0.25}, {"7": 0.8}],
    }
    service._embed_model = mock_model
    return service, mock_model


# ── Test: combined path matches the two separate paths ────────────────────────


def test_encode_dense_sparse_matches_separate_paths() -> None:
    """
    encode_dense_sparse returns dense vectors identical to encode_dense and sparse token lists
    identical to encode_sparse for the same input.
    """
    service, _ = _make_service_with_mock_model()
    texts = ["alpha", "beta"]

    dense_ref = service.encode_dense(texts, max_length=512)
    sparse_ref = service.encode_sparse(texts, max_length=512)

    dense, sparse = service.encode_dense_sparse(texts, max_length=512)

    assert dense == dense_ref
    assert sparse == sparse_ref
    # Wire shapes match what the two separate routes emit
    assert dense == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    assert sparse == [
        [{"index": 5, "value": 0.5}, {"index": 9, "value": 0.25}],
        [{"index": 7, "value": 0.8}],
    ]


# ── Test: exactly one forward pass ────────────────────────────────────────────


def test_encode_dense_sparse_uses_single_forward_pass() -> None:
    """
    encode_dense_sparse makes exactly ONE encode() call requesting both heads (return_dense and
    return_sparse True, return_colbert_vecs False) — not two passes.
    """
    service, mock_model = _make_service_with_mock_model()

    service.encode_dense_sparse(["gamma"], max_length=256)

    mock_model.encode.assert_called_once()
    _, kwargs = mock_model.encode.call_args
    assert kwargs["return_dense"] is True
    assert kwargs["return_sparse"] is True
    assert kwargs["return_colbert_vecs"] is False
    assert kwargs["max_length"] == 256


# ── Test: BGE_LOAD_RERANKER=false gate ─────────────────────────────────────────


def test_reranker_loaded_false_before_load() -> None:
    """A freshly-constructed service reports reranker_loaded=False before load() ever runs."""
    service = BgeModelsService(
        embed_model_id="stub-embed",
        rerank_model_id="stub-rerank",
        device_policy="cpu",
        fp16_requested=False,
    )
    assert service.reranker_loaded is False


def test_reranker_property_raises_when_gated_off() -> None:
    """
    With load_reranker=False, the `reranker` property raises a RuntimeError that names the
    gate explicitly — distinguishing "never going to load" from "not loaded yet".
    """
    service = BgeModelsService(
        embed_model_id="stub-embed",
        rerank_model_id="stub-rerank",
        device_policy="cpu",
        fp16_requested=False,
        load_reranker=False,
    )
    with pytest.raises(RuntimeError, match="BGE_LOAD_RERANKER=false"):
        _ = service.reranker


def test_max_concurrency_drops_to_one_when_reranker_gated_off() -> None:
    """
    Thread-budget auto-derivation only needs to account for rerank_lock contention when the
    reranker is actually loaded — with load_reranker=False, _max_concurrency must be 1, not 2.
    """
    service_with_reranker = BgeModelsService(
        embed_model_id="stub-embed",
        rerank_model_id="stub-rerank",
        device_policy="cpu",
        fp16_requested=False,
        load_reranker=True,
    )
    service_without_reranker = BgeModelsService(
        embed_model_id="stub-embed",
        rerank_model_id="stub-rerank",
        device_policy="cpu",
        fp16_requested=False,
        load_reranker=False,
    )
    assert service_with_reranker._max_concurrency == 2  # noqa: SLF001
    assert service_without_reranker._max_concurrency == 1  # noqa: SLF001
