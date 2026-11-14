# ====== Code Summary ======
# Characterization of the SDK's public import surface, recorded on the code as published (safety net
# of the R-24/R-25 module splits). A user installs ``docforge-sdk`` from PyPI and writes
# ``from docforge_sdk import ...`` / ``from docforge_sdk.resources.jobs import AsyncJobs``: the two
# ``__all__`` lists, where every exported name resolves, every resource class with its public methods
# and ``inspect.signature`` strings, and the two clients' wiring must stay byte-stable. A diff here is
# a public-contract decision (and a PyPI version question), never a test to fix.

# ====== Local Project Imports ======
from tests.characterization.support.golden import REGEN, assert_matches_golden, load_golden
from tests.characterization.support.surface import (
    clients_surface,
    discover_public_modules,
    module_surface,
    root_export_names,
)

_MODULES_GOLDEN = "public_modules.json"


def _published_modules() -> list[str]:
    """
    Name the modules the exports golden covers: the committed list, so a removed one fails loudly.

    Returns:
        list[str]: Dotted module paths; freshly discovered only when regenerating the goldens.
    """
    return discover_public_modules() if REGEN else load_golden(_MODULES_GOLDEN)


def test_root_and_models_all_lists_are_unchanged() -> None:
    assert_matches_golden("root_all.json", root_export_names())


def test_no_published_module_disappears() -> None:
    # A split may ADD modules; it must never drop or rename one a user can import today.
    discovered = discover_public_modules()
    if REGEN:
        assert_matches_golden(_MODULES_GOLDEN, discovered)
    assert set(load_golden(_MODULES_GOLDEN)) <= set(discovered)


def test_module_exports_resolve_the_same_way() -> None:
    snapshot = {name: module_surface(name) for name in _published_modules()}
    assert_matches_golden("module_exports.json", snapshot)


def test_clients_wire_the_same_resources_with_the_same_signatures() -> None:
    assert_matches_golden("clients.json", clients_surface())
