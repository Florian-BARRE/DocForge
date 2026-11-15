# ====== Code Summary ======
# Layer ratchet (docs/architecture.md §1, §4): dependencies point one way. (1) A router reaches the
# data stores only through the ``Database`` façade / ``facades`` (and the ORM row types of
# ``postgresql.tables``): never through a store client or its raw ``apis``; (2) the app and the worker
# are separate deployables that never import each other; (3) ``shared/`` (the engine, the public
# models, the services, the migrations) never imports the app or the worker. AST import scan, function-
# local imports included. It complements ``characterization/pipelines/test_import_graph.py`` (R-15),
# which pins the INSIDE of shared/libs (public_models, pipelines -> services, validation); this one pins
# the edges between the zones. The app and the worker each resolve ``backend``/``config`` to THEIR OWN
# tree (two roots, same names), so a cross-zone import can only be spelled ``app.…``/``worker.…`` or a
# relative import that climbs out of its zone: both are caught. A new bad edge is an architecture
# decision to make deliberately, never a test to loosen: ``_ROUTER_STORE_EDGES`` lists today's three.

# ====== Standard Library Imports ======
import pathlib

# ====== Third-Party Library Imports ======
import pytest

# ====== Local Project Imports ======
from .support.import_scan import SRC_ROOT, ImportRef, ImportScanner

_APP = SRC_ROOT / "app"
_WORKER = SRC_ROOT / "worker"
_ROUTERS = _APP / "backend" / "routers"
_SHARED = SRC_ROOT / "shared"

_STORE_MODULES = (
    "shared_libs.services.db.postgresql",
    "shared_libs.services.db.qdrant",
    "shared_libs.services.db.s3",
    "qdrant_client",
    "boto3",
    "aioboto3",
    "sqlalchemy",
    "psycopg",
    "asyncpg",
)
# The ORM row types (``postgresql.tables``) are shared DATA types, not store access: allowed.
_ROW_TYPES = "shared_libs.services.db.postgresql.tables"

# Pre-existing router -> store edges (file relative to src/docforge, module): TODAY'S REALITY, found
# when this ratchet was written. Each is a router/helper reaching below the façade; fixing one means
# adding a façade method and deleting the entry here. Never add one.
_ROUTER_STORE_EDGES: frozenset[tuple[str, str]] = frozenset(
    {
        # The raw job-api query helpers the jobs helpers use for the stream/list shaping.
        ("app/backend/routers/jobs/helpers.py", "shared_libs.services.db.postgresql.apis.job_api"),
        # Qdrant's reserved-payload keys + the collection api, used by the collection helpers.
        ("app/backend/routers/collections/helpers.py", "shared_libs.services.db.qdrant"),
        # The S3 object value type the document download streams.
        ("app/backend/routers/documents/router.py", "shared_libs.services.db.s3"),
    }
)


def _relative(path: pathlib.Path) -> str:
    return path.relative_to(SRC_ROOT).as_posix()


def _is_store_edge(ref: ImportRef) -> bool:
    if ref.level or not any(ImportScanner.under(ref.module, store) for store in _STORE_MODULES):
        return False
    if ImportScanner.under(ref.module, _ROW_TYPES):
        return False
    # ``from ...postgresql import tables`` is the row-types package, spelled one level up.
    return not (ref.module == "shared_libs.services.db.postgresql" and set(ref.names) == {"tables"})


def _router_store_edges() -> set[tuple[str, str]]:
    return {
        (_relative(path), ref.module)
        for path in ImportScanner.python_files(_ROUTERS)
        for ref in ImportScanner.imports_of(path)
        if _is_store_edge(ref)
    }


def _cross_zone_edges(zone: pathlib.Path, forbidden_roots: tuple[str, ...]) -> set[tuple[str, str]]:
    """(file, import) of every module of ``zone`` that imports a forbidden root, or whose relative
    import climbs out of the zone."""
    found: set[tuple[str, str]] = set()
    for path in ImportScanner.python_files(zone):
        for ref in ImportScanner.imports_of(path):
            if ref.level:
                target = ImportScanner.relative_target(path, ref)
                if zone not in (target, *target.parents):
                    found.add((_relative(path), "." * ref.level + ref.module))
            elif any(ImportScanner.under(ref.module, root) for root in forbidden_roots):
                found.add((_relative(path), ref.module))
    return found


def test_the_zones_are_scanned() -> None:
    """A moved zone must not turn the ratchet into a scan of nothing."""
    for zone in (_APP, _WORKER, _ROUTERS, _SHARED / "libs"):
        assert len(ImportScanner.python_files(zone)) > 20, zone


def test_routers_reach_the_stores_only_through_the_facade() -> None:
    """No NEW router import of a store client or its raw apis: use ``Database`` / a ``facades`` class."""
    new = sorted(_router_store_edges() - _ROUTER_STORE_EDGES)
    assert not new, (
        f"New router -> store edge(s): {new}. A router goes through the Database façade "
        "(docs/architecture.md §4): add a façade method instead of importing the store."
    )


def test_router_store_allowlist_has_no_stale_entry() -> None:
    """An allowlisted edge that disappeared leaves the allowlist, so the ratchet only tightens."""
    stale = sorted(_ROUTER_STORE_EDGES - _router_store_edges())
    assert not stale, f"_ROUTER_STORE_EDGES lists edges that no longer exist: {stale}"


def test_the_app_never_imports_the_worker() -> None:
    """app/ and worker/ are separate deployables: the app must not import the worker."""
    assert not _cross_zone_edges(_APP, ("worker",))


def test_the_worker_never_imports_the_app() -> None:
    """The worker must not import the app (its ``backend``/``config`` are its own tree)."""
    assert not _cross_zone_edges(_WORKER, ("app",))


@pytest.mark.parametrize("zone", ["libs", "migrations"])
def test_shared_never_imports_the_app_or_the_worker(zone: str) -> None:
    """shared/ is the layer BELOW app and worker: no import of them, of their ``backend``/``config``
    roots, nor a relative import that climbs out of shared/."""
    edges = _cross_zone_edges(_SHARED / zone, ("app", "worker", "backend", "config"))
    assert not edges, f"shared/{zone} must not depend on the app or the worker: {sorted(edges)}"
