# ====== Code Summary ======
# Structure guards of the model_server_core library (coding-standards, tests.md section 7): size, file
# header, no ML dependency, no logging/print bypass, no environment read outside the configuration,
# dependency list, a real package facade and the mirrored test tree. They read the sources, they never
# run the program.

# ====== Standard Library Imports ======
import ast
import pathlib
import tomllib

# ====== Third-Party Library Imports ======
import pytest

PROJECT = pathlib.Path(__file__).resolve().parents[2]
SOURCES = sorted((PROJECT / "model_server_core").rglob("*.py"))
TESTS = sorted((PROJECT / "tests").rglob("*.py"))
MAX_LINES = 400
BANNED_ML_ROOTS = {"torch", "torchvision", "paddle", "paddleocr", "paddlex", "transformers"}
ALLOWED_DEPENDENCIES = {"fastapi", "uvicorn", "pydantic", "configplusplus", "loggerplusplus"}
# Only these optional libraries may be imported, lazily (inside a function), by a decoder.
LAZY_OPTIONAL_ROOTS = {"PIL", "pypdfium2"}


def _relative(path: pathlib.Path) -> str:
    return str(path.relative_to(PROJECT))


def _top_level_imports(tree: ast.Module) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def _module_level_roots(tree: ast.Module) -> set[str]:
    """Root packages imported at module level (not inside a function or class)."""
    roots: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("path", SOURCES + TESTS, ids=_relative)
def test_no_file_exceeds_the_size_limit(path: pathlib.Path) -> None:
    assert len(path.read_text().splitlines()) <= MAX_LINES, f"{_relative(path)}: split the unit"


@pytest.mark.parametrize("path", [p for p in SOURCES if p.name != "__init__.py"], ids=_relative)
def test_every_module_opens_with_a_code_summary(path: pathlib.Path) -> None:
    assert path.read_text().startswith("# ====== Code Summary ======"), _relative(path)


@pytest.mark.parametrize("path", SOURCES, ids=_relative)
def test_the_core_imports_no_ml_library(path: pathlib.Path) -> None:
    imported = _top_level_imports(ast.parse(path.read_text()))

    assert not imported & BANNED_ML_ROOTS, f"{_relative(path)} imports a model library"


@pytest.mark.parametrize("path", SOURCES, ids=_relative)
def test_optional_libraries_are_only_imported_lazily(path: pathlib.Path) -> None:
    tree = ast.parse(path.read_text())
    module_level = _module_level_roots(tree)

    assert not module_level & LAZY_OPTIONAL_ROOTS, f"{_relative(path)}: import it inside the method"


@pytest.mark.parametrize("path", SOURCES, ids=_relative)
def test_no_print_and_no_standard_logging_bypass(path: pathlib.Path) -> None:
    tree = ast.parse(path.read_text())
    calls_print = any(
        isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"
        for node in ast.walk(tree)
    )

    assert not calls_print, f"{_relative(path)} prints"
    assert "logging" not in _top_level_imports(tree), f"{_relative(path)} uses stdlib logging"


@pytest.mark.parametrize("path", SOURCES, ids=_relative)
def test_the_environment_is_never_read_directly(path: pathlib.Path) -> None:
    source = path.read_text()

    assert "os.environ" not in source and "getenv" not in source, _relative(path)


def test_runtime_dependencies_are_exactly_the_allowed_five() -> None:
    declared = tomllib.loads((PROJECT / "pyproject.toml").read_text())["project"]["dependencies"]
    names = {
        entry.split("[")[0].split(">")[0].split("<")[0].split("=")[0].strip() for entry in declared
    }

    assert names == ALLOWED_DEPENDENCIES


@pytest.mark.parametrize(
    "path", [p for p in SOURCES if p.name == "__init__.py" and p.parent != PROJECT], ids=_relative
)
def test_every_facade_declares_all_and_holds_no_logic(path: pathlib.Path) -> None:
    body = ast.parse(path.read_text()).body
    declares_all = any(
        isinstance(node, ast.Assign)
        and any(getattr(t, "id", "") == "__all__" for t in node.targets)
        for node in body
    )
    only_reexports = all(isinstance(node, (ast.ImportFrom, ast.Assign)) for node in body)

    assert declares_all and only_reexports, f"{_relative(path)} must only re-export"


def test_every_public_name_of_the_facade_resolves() -> None:
    import model_server_core

    for name in model_server_core.__all__:
        assert hasattr(model_server_core, name), name


def test_the_tests_mirror_the_source_packages() -> None:
    packages = {p.name for p in (PROJECT / "model_server_core").iterdir() if p.is_dir()}
    test_dirs = {
        p.name
        for p in (PROJECT / "tests").iterdir()
        if p.is_dir() and p.name not in {"support", "structure", "__pycache__"}
    }

    assert test_dirs <= packages, f"test folders without a source package: {test_dirs - packages}"


def test_support_holds_no_test_module() -> None:
    offenders = [_relative(p) for p in (PROJECT / "tests" / "support").rglob("test_*.py")]

    assert offenders == []
