# ====== Code Summary ======
# Import-graph guard of the pipelines package (R-15). It parses every module of shared/libs with `ast`
# — function-local imports included, because those are exactly how the validation <-> ingest/search
# cycle used to hide — and asserts the allowed edges only: the public models import nothing of the
# pipelines; the pipelines never import the services layer (one named, pure exception); the validation
# package never imports the ingest or search facades. A new edge here is an architecture decision to
# make deliberately (docs/architecture.md), never a test to loosen.

# ====== Standard Library Imports ======
import ast
import pathlib

# ====== Third-Party Library Imports ======
import pytest

SHARED_LIBS = pathlib.Path(__file__).resolve().parents[4] / "shared" / "libs"
PIPELINES = SHARED_LIBS / "pipelines"

# The ONLY pipelines -> services edge left: the preview projector flattens the execution record with
# the PURE ExecutionTreeFlattener, which still lives in services/db/trace (R-10). Moving that
# flattener next to the engine's NodeExecutionRecord removes this entry (follow-up, not R-15).
ALLOWED_SERVICES_EDGES = {
    ("preview/projector.py", "shared_libs.services.db.trace"),
}

# The ONE lazy edge from validation to the composition root: BlobStructureValidator's default palette
# source when none is injected. It is not the ingest/search facades themselves.
ALLOWED_VALIDATION_COMPOSITION_EDGES = {
    ("blob.py", "shared_libs.pipelines.pipeline_registry"),
}


def _module_name(path: pathlib.Path) -> str:
    """Dotted module name (``shared_libs.<...>``) of a file under shared/libs."""
    parts = path.relative_to(SHARED_LIBS).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(("shared_libs", *parts))


def _is_module(name: str) -> bool:
    """True when the dotted ``shared_libs...`` name is a module or package of shared/libs."""
    base = SHARED_LIBS.joinpath(*name.split(".")[1:])
    return base.with_suffix(".py").is_file() or base.joinpath("__init__.py").is_file()


def _imports_of(path: pathlib.Path) -> set[str]:
    """Every absolute module a file imports, anywhere in its body (relative ones resolved)."""
    module = _module_name(path)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.rsplit(".", node.level - 1)[0] if node.level > 1 else package
                target = f"{base}.{node.module}" if node.module else base
            else:
                target = node.module or ""
            found.add(target)
            # `from pkg import submodule` imports a submodule: keep it as an edge too.
            found.update(
                f"{target}.{alias.name}"
                for alias in node.names
                if _is_module(f"{target}.{alias.name}")
            )
    return found


def _under(modules: set[str], prefix: str) -> set[str]:
    """The modules equal to ``prefix`` or below it."""
    return {name for name in modules if name == prefix or name.startswith(f"{prefix}.")}


def _files(root: pathlib.Path) -> list[pathlib.Path]:
    return sorted(root.rglob("*.py"))


def test_public_models_import_nothing_of_the_pipelines() -> None:
    """public_models is the lowest layer: it never depends on the pipelines (or the services)."""
    offenders = {
        f"{path.relative_to(SHARED_LIBS)} -> {name}"
        for path in _files(SHARED_LIBS / "public_models")
        for prefix in ("shared_libs.pipelines", "shared_libs.services")
        for name in _under(_imports_of(path), prefix)
    }
    assert not offenders, f"public_models must not import pipelines/services: {sorted(offenders)}"


def test_pipelines_never_import_the_services_layer_except_the_named_edge() -> None:
    """pipelines -> services.db is inverted: the layers point services -> pipelines only."""
    edges = {
        (path.relative_to(PIPELINES).as_posix(), name)
        for path in _files(PIPELINES)
        for name in _under(_imports_of(path), "shared_libs.services")
    }
    unexpected = {edge for edge in edges if edge not in ALLOWED_SERVICES_EDGES}
    assert not unexpected, f"new pipelines -> services edge(s): {sorted(unexpected)}"
    assert not any("source_resolver" in file for file, _ in edges), "the DB read port was undone"


@pytest.mark.parametrize("forbidden", ["ingest", "search"])
def test_validation_does_not_import_the_ingest_or_search_facades(forbidden: str) -> None:
    """The ingest and search facades import validation, so validation must not import them back."""
    prefix = f"shared_libs.pipelines.{forbidden}"
    offenders = {
        f"{path.relative_to(PIPELINES)} -> {name}"
        for path in _files(PIPELINES / "validation")
        for name in _under(_imports_of(path), prefix)
    }
    assert not offenders, f"validation <-> {forbidden} cycle: {sorted(offenders)}"


def test_validation_reaches_the_composition_root_only_through_the_named_seam() -> None:
    """The one lazy edge validation keeps is to the registry, never to a facade."""
    edges = {
        (path.relative_to(PIPELINES / "validation").as_posix(), name)
        for path in _files(PIPELINES / "validation")
        for name in _under(_imports_of(path), "shared_libs.pipelines.pipeline_registry")
    }
    assert edges == ALLOWED_VALIDATION_COMPOSITION_EDGES


def test_the_facades_still_import_validation_one_way() -> None:
    """Sanity: the legitimate direction (ingest/search -> validation) is still what the guard sees."""
    for facade in ("ingest", "search"):
        imports = _imports_of(PIPELINES / facade / "pipeline.py")
        assert _under(imports, "shared_libs.pipelines.validation"), facade
