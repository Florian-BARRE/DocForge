# ====== Code Summary ======
# Drift guard for the R-25 codegen: the committed sync modules (the transport and every resource's
# ``sync_*.py``) must equal what ``scripts/generate_sync.py`` derives from their async twins, each
# async module must have a generated twin, and the transform itself keeps its contract (async syntax
# dropped, ``AsyncX`` renamed, prose left alone). Editing a sync file by hand fails this test.

# ====== Standard Library Imports ======
import ast
import importlib.util
import shutil
import sys
from pathlib import Path
from types import ModuleType

# ====== Third-Party Library Imports ======
import pytest

_SDK_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE = _SDK_ROOT / "docforge_sdk"


def _load_generator() -> ModuleType:
    """Import ``scripts/generate_sync.py`` (``scripts/`` is not a package) by file path."""
    spec = importlib.util.spec_from_file_location(
        "generate_sync", _SDK_ROOT / "scripts" / "generate_sync.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


generate_sync = _load_generator()
_CODEGEN = generate_sync.SyncCodegen()
_TARGETS = _CODEGEN.targets()

_ASYNC_SAMPLE = '''\
# ====== Code Summary ======
# The asynchronous demo resource: the awaiting shell over the shared specs.

# ====== Standard Library Imports ======
from collections.abc import AsyncIterator


class AsyncDemo(AsyncResource):
    """Asynchronous demo; the server runs the job asynchronously and we await nothing here."""

    async def get(self, key: str) -> int:
        """Fetch (this await in a docstring stays)."""
        value = await self._transport.request(key)
        async with self._lock:
            return value

    async def stream(self) -> AsyncIterator[bytes]:
        """Stream the chunks."""
        async for chunk in self._transport.stream_get("/x"):
            yield chunk


__all__ = ["AsyncDemo"]
'''


@pytest.mark.parametrize("target", _TARGETS, ids=lambda t: t.output.name)
def test_committed_sync_file_equals_the_generator_output(target: object) -> None:
    """The committed sync file is byte-identical to the regenerated one: no hand edit, no stale file."""
    assert target.output.read_text(encoding="utf-8") == _CODEGEN.render(target), (  # type: ignore[attr-defined]
        "stale sync module: run `uv run python scripts/generate_sync.py` from src/docforge_sdk"
    )


def test_every_async_resource_module_has_a_generated_twin() -> None:
    """Each ``resources/*/async_*.py`` is a codegen source, so no async module is left unmirrored."""
    sources = {t.source for t in _TARGETS}
    on_disk = set((_PACKAGE / "resources").glob("*/async_*.py"))
    assert on_disk and on_disk <= sources
    assert _PACKAGE / "_transport_async.py" in sources


@pytest.mark.parametrize("target", _TARGETS, ids=lambda t: t.output.name)
def test_generated_module_has_no_async_syntax_and_a_generated_notice(target: object) -> None:
    """A sync module defines no coroutine, awaits nothing and says it is generated."""
    text = target.output.read_text(encoding="utf-8")  # type: ignore[attr-defined]
    assert "GENERATED FILE — DO NOT EDIT" in text.split("\n\n", 1)[0]
    banned = (ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith, ast.Await)
    assert not [n for n in ast.walk(ast.parse(text)) if isinstance(n, banned)]


def test_transform_drops_async_syntax_and_renames_async_classes() -> None:
    """``async``/``await`` go, ``AsyncX`` becomes ``SyncX`` (also as a string), the stream stays a generator."""
    transformer = generate_sync.SyncTransformer()
    derived = transformer.transform(_ASYNC_SAMPLE, "async_demo.py", ())

    assert "async def" not in derived and "async for" not in derived and "async with" not in derived
    assert "= self._transport.request(key)" in derived
    assert "    def get(self, key: str) -> int:" in derived
    assert "    def stream(self) -> Iterator[bytes]:" in derived
    assert "for chunk in self._transport.stream_get" in derived
    assert "class SyncDemo(SyncResource):" in derived
    assert '__all__ = ["SyncDemo"]' in derived
    ast.parse(derived)


def test_transform_rewrites_the_class_docstring_and_header_only() -> None:
    """The class docstring's first word and the Code Summary are re-worded; method prose is kept."""
    derived = generate_sync.SyncTransformer().transform(_ASYNC_SAMPLE, "async_demo.py", ())

    assert '"""Synchronous demo; the server runs the job asynchronously' in derived
    assert "(this await in a docstring stays)" in derived
    assert "# The synchronous demo resource: the blocking shell over the shared specs." in derived
    assert "# GENERATED FILE — DO NOT EDIT. Derived from async_demo.py" in derived


def test_transform_refuses_a_module_without_a_code_summary() -> None:
    """A source without the Code Summary block cannot carry the generated notice: fail loudly."""
    with pytest.raises(ValueError, match="Code Summary"):
        generate_sync.SyncTransformer().transform("x = 1\n", "async_bad.py", ())


def test_drift_is_detected_and_rewritten(tmp_path: Path) -> None:
    """A stale or missing sync file is reported by ``drifted`` and fixed by ``write``."""
    package = tmp_path / "docforge_sdk"
    resource = package / "resources" / "demo"
    resource.mkdir(parents=True)
    shutil.copy(_PACKAGE / "_transport_async.py", package / "_transport_async.py")
    shutil.copy(_PACKAGE / "resources" / "health" / "async_health.py", resource / "async_health.py")
    codegen = generate_sync.SyncCodegen(package, _SDK_ROOT)
    stale_output = resource / "sync_health.py"
    stale_output.write_text("# hand-edited\n", encoding="utf-8")

    assert {p.name for p in codegen.drifted()} == {"_transport_sync.py", "sync_health.py"}
    assert {p.name for p in codegen.write()} == {"_transport_sync.py", "sync_health.py"}
    assert codegen.drifted() == []
    assert stale_output.read_text(encoding="utf-8") == (
        _PACKAGE / "resources" / "health" / "sync_health.py"
    ).read_text(encoding="utf-8")
