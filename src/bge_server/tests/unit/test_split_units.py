# ====== Code Summary ======
# Unit tests for the units split out of the batching engine, the models service and the lifespan
# (R-28): the per-kind BatchProcessors (scatter shapes, abandoned-work skipping, error isolation),
# the BgeModelLoader (concurrency/thread resolution, reranker gate) and the removal of the dead
# compute_rerank_scores wrapper, plus a guard that every unit stays within 400 lines.

# ====== Standard Library Imports ======
import asyncio
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from libs.batching.models import EmbedAllItem, EmbedItem, RerankItem
from libs.batching.processors import DenseProcessor, EmbedAllProcessor, RerankProcessor
from libs.bge_models.model_loader import BgeModelLoader
from libs.bge_models.service import BgeModelsService

_ROOT = Path(__file__).resolve().parents[2]


def _processor(cls: type, models: MagicMock, sub_batch_size: int = 0, **kwargs: int):
    """Build a processor with a fresh gate and lock."""
    return cls(models, asyncio.Semaphore(1), asyncio.Lock(), sub_batch_size, **kwargs)


# ── Processors ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dense_processor_scatters_slices_per_item() -> None:
    """Each item's future gets its own slice of the flat dense results, in order."""
    models = MagicMock()
    models.encode_dense.side_effect = lambda texts, _max: [[float(len(t))] for t in texts]
    loop = asyncio.get_running_loop()
    a = EmbedItem(future=loop.create_future(), cost=2, texts=["x", "yy"])
    b = EmbedItem(future=loop.create_future(), cost=1, texts=["zzz"])

    await _processor(DenseProcessor, models, max_length=64).process([a, b])

    assert a.future.result() == [[1.0], [2.0]]
    assert b.future.result() == [[3.0]]
    models.encode_dense.assert_called_once_with(["x", "yy", "zzz"], 64)


@pytest.mark.asyncio
async def test_embed_all_processor_splits_pairs_into_dense_and_sparse() -> None:
    """embed_all resolves to a (dense_list, sparse_list) tuple from one combined call."""
    models = MagicMock()
    models.encode_dense_sparse.return_value = ([[1.0], [2.0]], [[{"index": 1, "value": 0.5}], []])
    item = EmbedAllItem(future=asyncio.get_running_loop().create_future(), cost=2, texts=["a", "b"])

    await _processor(EmbedAllProcessor, models, max_length=8).process([item])

    assert item.future.result() == ([[1.0], [2.0]], [[{"index": 1, "value": 0.5}], []])


@pytest.mark.asyncio
async def test_rerank_processor_renumbers_and_sorts_per_request() -> None:
    """Indices restart at 0 per request and results are sorted score-descending."""
    models = MagicMock()
    models.compute_rerank_scores_flat.return_value = [0.1, 0.9, 0.5]
    loop = asyncio.get_running_loop()
    a = RerankItem(future=loop.create_future(), cost=2, query="q1", texts=["t1", "t2"])
    b = RerankItem(future=loop.create_future(), cost=1, query="q2", texts=["t3"])

    await _processor(RerankProcessor, models).process([a, b])

    assert a.future.result() == [{"index": 1, "score": 0.9}, {"index": 0, "score": 0.1}]
    assert b.future.result() == [{"index": 0, "score": 0.5}]
    models.compute_rerank_scores_flat.assert_called_once_with(
        [["q1", "t1"], ["q1", "t2"], ["q2", "t3"]]
    )


@pytest.mark.asyncio
async def test_processor_skips_sub_batches_nobody_waits_for() -> None:
    """A sub-batch whose every owner is cancelled is skipped; live owners are still served."""
    models = MagicMock()
    models.encode_dense.side_effect = lambda texts, _max: [[1.0] for _ in texts]
    loop = asyncio.get_running_loop()
    dead = EmbedItem(future=loop.create_future(), cost=1, texts=["dead"])
    live = EmbedItem(future=loop.create_future(), cost=1, texts=["live"])
    dead.future.cancel()

    await _processor(DenseProcessor, models, sub_batch_size=1, max_length=8).process([dead, live])

    models.encode_dense.assert_called_once_with(["live"], 8)
    assert live.future.result() == [[1.0]]


@pytest.mark.asyncio
async def test_processor_sets_model_failure_on_every_pending_future() -> None:
    """A model failure is distributed to all futures so no request hangs."""
    models = MagicMock()
    models.encode_dense.side_effect = RuntimeError("boom")
    loop = asyncio.get_running_loop()
    items = [EmbedItem(future=loop.create_future(), cost=1, texts=["t"]) for _ in range(2)]

    await _processor(DenseProcessor, models, max_length=8).process(list(items))

    for item in items:
        with pytest.raises(RuntimeError, match="boom"):
            item.future.result()


# ── Loader ────────────────────────────────────────────────────────────────────


def _fake_ml_stack(monkeypatch: pytest.MonkeyPatch) -> tuple[MagicMock, MagicMock]:
    """Install fake torch / FlagEmbedding modules; return the two model-class mocks."""
    torch = types.ModuleType("torch")
    torch.set_num_threads = MagicMock()  # type: ignore[attr-defined]
    torch.cuda = types.SimpleNamespace(is_available=lambda: False)  # type: ignore[attr-defined]
    flag = types.ModuleType("FlagEmbedding")
    flag.BGEM3FlagModel = MagicMock(name="BGEM3FlagModel")  # type: ignore[attr-defined]
    flag.FlagReranker = MagicMock(name="FlagReranker")  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "FlagEmbedding", flag)
    return flag.BGEM3FlagModel, flag.FlagReranker  # type: ignore[attr-defined]


def _loader(**overrides: object) -> BgeModelLoader:
    params: dict[str, object] = dict(
        embed_model_id="e",
        rerank_model_id="r",
        device_policy="cpu",
        fp16_requested=False,
        torch_num_threads=3,
        embed_revision=None,
        rerank_revision=None,
        load_reranker=True,
        max_concurrent=0,
        initial_max_concurrency=2,
    )
    params.update(overrides)
    return BgeModelLoader(**params)  # type: ignore[arg-type]


def test_loader_builds_both_models_and_resolves_cpu_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On CPU with auto concurrency the cap is 1 and both models are constructed."""
    embed_cls, rerank_cls = _fake_ml_stack(monkeypatch)

    loaded = _loader().load()

    assert (loaded.device, loaded.use_fp16, loaded.max_concurrency) == ("cpu", False, 1)
    assert loaded.embed_model is embed_cls.return_value
    assert loaded.reranker is rerank_cls.return_value
    embed_cls.assert_called_once_with("e", use_fp16=False, devices="cpu")
    sys.modules["torch"].set_num_threads.assert_called_once_with(3)  # type: ignore[attr-defined]


def test_loader_skips_reranker_when_gated_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """load_reranker=False never constructs the reranker and caps concurrency at 1."""
    _, rerank_cls = _fake_ml_stack(monkeypatch)

    loaded = _loader(load_reranker=False, max_concurrent=4).load()

    assert loaded.reranker is None
    assert loaded.max_concurrency == 1
    rerank_cls.assert_not_called()


def test_service_load_stores_loader_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    """BgeModelsService.load() exposes the loaded models and resolved state through its API."""
    embed_cls, _ = _fake_ml_stack(monkeypatch)
    service = BgeModelsService("e", "r", "cpu", False, torch_num_threads=2)

    service.load()

    assert service.embed_model is embed_cls.return_value
    assert service.reranker_loaded is True
    assert (service.resolved_device, service.max_concurrency) == ("cpu", 1)
    service.unload()
    assert service.reranker_loaded is False


# ── Structure ─────────────────────────────────────────────────────────────────


def test_dead_compute_rerank_scores_wrapper_is_gone() -> None:
    """Only the flat scoring entry point used by the batching engine remains."""
    assert not hasattr(BgeModelsService, "compute_rerank_scores")
    assert hasattr(BgeModelsService, "compute_rerank_scores_flat")


def test_split_units_stay_within_400_lines() -> None:
    """Every unit of the batching, models and lifespan packages is at most 400 lines."""
    paths = [*(_ROOT / "libs").rglob("*.py"), _ROOT / "backend" / "lifespan.py"]
    too_long = {
        str(p.relative_to(_ROOT)): n for p in paths if (n := len(p.read_text().splitlines())) > 400
    }
    assert too_long == {}
