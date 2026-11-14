# ====== Code Summary ======
# Structure guard for the R-24 split of the oversized resource/model modules: each split module is a
# package whose ``__init__`` re-exports its classes at the path they always had, no SDK source file
# under ``resources/`` or ``models/`` exceeds the 400-line unit size, and ``pin_module_path`` only
# rewrites the ``__module__`` of classes defined in a sub-module of the package.

# ====== Standard Library Imports ======
import importlib
from pathlib import Path

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
import docforge_sdk
from docforge_sdk.models._reexport import pin_module_path

_SDK_ROOT = Path(docforge_sdk.__file__).parent
_MAX_LINES = 400
# The aggregator only lists imports and the public ``__all__``; it stays one file by design.
_AGGREGATORS = {Path("models/__init__.py")}
_SPLIT_PACKAGES = (
    "docforge_sdk.models.jobs",
    "docforge_sdk.models.collections",
    "docforge_sdk.models.explorer",
    "docforge_sdk.models.search",
    "docforge_sdk.resources.collections",
    "docforge_sdk.resources.jobs",
    "docforge_sdk.resources.explorer",
)


def _source_files() -> list[Path]:
    """List the SDK source files whose size is bounded (``resources/`` and ``models/``)."""
    files = [*(_SDK_ROOT / "resources").rglob("*.py"), *(_SDK_ROOT / "models").rglob("*.py")]
    return sorted(f for f in files if f.relative_to(_SDK_ROOT) not in _AGGREGATORS)


@pytest.mark.parametrize("path", _source_files(), ids=lambda p: str(p.relative_to(_SDK_ROOT)))
def test_source_file_fits_the_unit_size(path: Path) -> None:
    """No resource or model source file exceeds the 400-line unit size."""
    assert len(path.read_text().splitlines()) <= _MAX_LINES


@pytest.mark.parametrize("package_name", _SPLIT_PACKAGES)
def test_split_package_keeps_its_import_path(package_name: str) -> None:
    """No exported class reports a sub-module path: each keeps the pre-split package path."""
    package = importlib.import_module(package_name)
    assert hasattr(package, "__path__"), "a split module is a package"
    for name in package.__all__:
        exported = getattr(package, name)
        assert not exported.__module__.startswith(f"{package_name}."), name


def test_pin_module_path_only_pins_classes_of_a_submodule() -> None:
    """A class of a sub-module is pinned; a foreign class, a constant and a pinned class are left."""

    class Inner:
        __module__ = "pkg.sub"

    class Foreign:
        __module__ = "other.mod"

    namespace = {"Inner": Inner, "Foreign": Foreign, "CONST": "x"}
    pin_module_path("pkg", namespace, list(namespace))

    assert Inner.__module__ == "pkg"
    assert Foreign.__module__ == "other.mod"
    assert namespace["CONST"] == "x"
