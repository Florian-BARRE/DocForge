"""Unit tests for DotsOcrEngine._ensure_model's partial-init robustness (pure, offline, no GPU).

Regression for the prod incident where a processor-load failure left the engine with a loaded model
but a None processor: the old guard (``if self._model is None``) then skipped re-init forever, so every
subsequent parse crashed with ``'NoneType' object has no attribute 'apply_chat_template'`` instead of
the real load error. The load must be atomic — publish both only after both succeed, reset + re-raise
on any failure — so the engine self-heals and the genuine error always surfaces.

transformers/torch are imported lazily INSIDE _ensure_model, so the tests inject fakes via sys.modules
and never touch a real model or a GPU.
"""

import os
import sys
import types

import pytest

from libs.dots_ocr.engine import DotsOcrEngine


def _engine() -> DotsOcrEngine:
    """A cheap engine instance (the constructor stores args only — no model is loaded).

    Pre-sets ``_local_model_dir`` so ``_ensure_model`` skips the real weight resolution/download — these
    tests exercise the atomic model+processor load, not the dot-free-dir materialisation (covered
    separately below).
    """
    engine = DotsOcrEngine(
        model_path="fake/dots.ocr",
        model_cache_home="/tmp/dots-cache",
        render_dpi=100,
        max_pages=0,
        max_tokens=16,
        image_factor=28,
        min_pixels=3136,
        max_pixels=11289600,
    )
    engine._local_model_dir = "/fake/DotsOCR"
    return engine


def _install_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    model: object,
    processor_exc: Exception | None,
    processor: object,
) -> None:
    """Inject fake ``torch`` + ``transformers`` modules the lazy import inside _ensure_model resolves."""
    fake_torch = types.SimpleNamespace(float16="float16")

    class _FakeAutoModel:
        @staticmethod
        def from_pretrained(*_args: object, **_kwargs: object) -> object:
            return model

    class _FakeAutoProcessor:
        @staticmethod
        def from_pretrained(*_args: object, **_kwargs: object) -> object:
            if processor_exc is not None:
                raise processor_exc
            return processor

    fake_transformers = types.SimpleNamespace(
        AutoModelForCausalLM=_FakeAutoModel, AutoProcessor=_FakeAutoProcessor
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)


def test_processor_failure_resets_engine_and_reraises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A processor-load failure must reset BOTH handles and re-raise — never leave a lone model."""
    engine = _engine()
    fake_model = types.SimpleNamespace(eval=lambda: None)
    _install_fakes(
        monkeypatch, model=fake_model, processor_exc=RuntimeError("processor boom"), processor=None
    )

    with pytest.raises(RuntimeError, match="processor boom"):
        engine._ensure_model()

    # The engine is fully reset — not wedged with a model but no processor (the prod bug).
    assert engine._model is None
    assert engine._processor is None
    assert engine.warmed is False


def test_retry_after_failure_can_fully_load(monkeypatch: pytest.MonkeyPatch) -> None:
    """After a transient processor failure the NEXT call retries from scratch and fully loads."""
    engine = _engine()
    fake_model = types.SimpleNamespace(eval=lambda: None)

    # 1. First attempt: processor raises → engine reset, error surfaced.
    _install_fakes(
        monkeypatch, model=fake_model, processor_exc=RuntimeError("transient"), processor=None
    )
    with pytest.raises(RuntimeError):
        engine._ensure_model()
    assert engine.warmed is False

    # 2. Second attempt (failure gone): both load and are published together.
    fake_processor = object()
    _install_fakes(monkeypatch, model=fake_model, processor_exc=None, processor=fake_processor)
    engine._ensure_model()
    assert engine._model is fake_model
    assert engine._processor is fake_processor
    assert engine.warmed is True


def test_ensure_model_is_idempotent_once_warm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Once both are loaded, a second call must NOT reload (guard requires both present)."""
    engine = _engine()
    fake_model = types.SimpleNamespace(eval=lambda: None)
    fake_processor = object()
    _install_fakes(monkeypatch, model=fake_model, processor_exc=None, processor=fake_processor)

    engine._ensure_model()

    # A second call reloads nothing: swap the fakes to raise; a compliant guard never calls them.
    def _boom(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("must not reload a warm engine")

    monkeypatch.setattr(sys.modules["transformers"].AutoModelForCausalLM, "from_pretrained", _boom)
    monkeypatch.setattr(sys.modules["transformers"].AutoProcessor, "from_pretrained", _boom)
    engine._ensure_model()  # no exception → the guard short-circuited
    assert engine.warmed is True


# ── _resolve_local_model_dir — the dot-free-dir workaround for dots.ocr's dotted repo id ─────────────


def _fresh_engine(model_path: str, cache_home: str) -> DotsOcrEngine:
    """An engine WITHOUT the _local_model_dir bypass, to exercise the real resolution."""
    return DotsOcrEngine(
        model_path=model_path,
        model_cache_home=cache_home,
        render_dpi=100,
        max_pages=0,
        max_tokens=16,
        image_factor=28,
        min_pixels=3136,
        max_pixels=11289600,
    )


def test_resolve_passes_through_a_dotfree_local_dir(tmp_path) -> None:
    """A local dir whose leaf has no '.' is safe as-is — used verbatim, no download."""
    model_dir = tmp_path / "DotsOCR"
    model_dir.mkdir()
    engine = _fresh_engine(str(model_dir), str(tmp_path / "cache"))

    assert engine._resolve_local_model_dir() == str(model_dir)


def test_resolve_downloads_a_dotted_hub_id_to_a_dotfree_dir(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dots.ocr case: a dotted hub id is snapshot-downloaded into a dot-free local dir, and THAT
    (no '.' in its leaf) is what gets loaded — the fix for the transformers_modules import break."""
    calls: dict[str, object] = {}

    def _fake_snapshot_download(*, repo_id: str, local_dir: str) -> str:
        calls["repo_id"] = repo_id
        calls["local_dir"] = local_dir
        return local_dir

    fake_hub = types.SimpleNamespace(snapshot_download=_fake_snapshot_download)
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hub)

    cache = tmp_path / "cache"
    engine = _fresh_engine("rednote-hilab/dots.ocr", str(cache))
    resolved = engine._resolve_local_model_dir()

    assert calls["repo_id"] == "rednote-hilab/dots.ocr"
    # Materialised under the cache, with the '.' sanitised out of the leaf.
    assert resolved == str(cache / "local_models" / "dots_ocr")
    assert "." not in os.path.basename(resolved)
    # Cached: a second call returns the same path without re-downloading.
    calls.clear()
    assert engine._resolve_local_model_dir() == resolved
    assert calls == {}
