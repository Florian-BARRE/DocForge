# ====== Code Summary ======
# IR-canonical ratchet (charter invariant: "the IR is the only source of truth; Markdown/PDF/HTML are
# generated views", docs/architecture.md §1). Five structural, checkable facts pin it:
#   1. the canonical IR classes (``DocumentIR``, ``Block``, ``TableData``…) are DEFINED only in
#      ``shared/libs/public_models/ir`` (one pydantic definition each; no second copy to drift);
#   2. the view generators (``pipelines/ingest/linearize``: markdown/HTML) take a ``DocumentIR`` as the
#      document input of every public method and return a ``str``: a view is a pure function of the IR;
#   3. the IR package is the lowest layer: it imports no view generator, no pipeline, no service
#      (and the generators import only the public models, never a store);
#   4. only the read-side explorer endpoint calls the generators: no worker, no façade, no pipeline node
#      can ingest a rendered view, so nothing can persist one back as the IR;
#   5. no NEW database column is named like a stored view (``markdown``/``html``/``linearized``); the one
#      pre-existing (``block_table.linearized_md``) is allowlisted and ingest only ever writes ``None`` to it.
# This is the strongest CODE-LEVEL form of the invariant: "no code writes a rendered string into the IR"
# is not statically decidable in general, so it is pinned by 1+4+5 (the producer and every possible
# consumer of a view are enumerated; a new consumer is an explicit decision in ``_VIEW_CONSUMERS``).

# ====== Standard Library Imports ======
import ast
import pathlib

# ====== Local Project Imports ======
from .support.import_scan import SRC_ROOT, ImportScanner

_LIBS = SRC_ROOT / "shared" / "libs"
_IR = _LIBS / "public_models" / "ir"
_LINEARIZE = _LIBS / "pipelines" / "ingest" / "linearize"
_TABLES = _LIBS / "services" / "db" / "postgresql" / "tables"
_PRODUCT_ZONES = (SRC_ROOT / "app", SRC_ROOT / "worker", _LIBS)

# Classes that share a name with an IR class but are NOT the IR: the SQLAlchemy persistence ROW of a
# block (the façades alias it ``BlockRow``; the IR is rebuilt from it by ``IRBundleAdapter``).
_NON_IR_NAMESAKES: frozenset[tuple[str, str]] = frozenset(
    {("shared/libs/services/db/postgresql/tables/ir/block.py", "Block")}
)

# The ONLY modules that import the view generators (relative to src/docforge): the explorer's read
# endpoint, which linearizes an IR it just loaded and wraps the string in a Response. Never persisted.
_VIEW_CONSUMERS: frozenset[str] = frozenset({"app/backend/routers/explorer/views.py"})

_LINEARIZE_MODULE = "shared_libs.pipelines.ingest.linearize"
# What the IR package may import: pydantic, the stdlib, and its own siblings / ``..base``.
_IR_ALLOWED_ROOTS = frozenset({"pydantic", "enum", "dataclasses", "typing"})
# What a view generator may import: the public models and the logger (+ stdlib), nothing else shared.
_LINEARIZE_ALLOWED_ROOTS = frozenset(
    {"loggerplusplus", "abc", "html", "re", "typing", "__future__"}
)
_STORED_VIEW_WORDS = ("markdown", "html", "linearized")

# Pre-existing stored-view-looking column (file, attribute): ``BlockTable.linearized_md``, a nullable
# "deterministic markdown rendering" of a table, exposed read-only by the explorer. INGEST NEVER FILLS IT
# (see ``_BLOCK_TABLE_WRITERS``); dropping the column (a migration, out of this ratchet) removes the entry.
_STORED_VIEW_COLUMNS: frozenset[tuple[str, str]] = frozenset(
    {("shared/libs/services/db/postgresql/tables/ir/block_table.py", "linearized_md")}
)
# Every place that builds a ``BlockTable`` row -> how it fills ``linearized_md``: the ingest translator
# stores None; the transfer restore copies the (None) value of the bundle it exported.
_BLOCK_TABLE_WRITERS: dict[str, str] = {
    "worker/backend/libs/persistence/translator.py": "none",
    "worker/backend/libs/collection_transfer/restore/rows.py": "copy",
}


def _relative(path: pathlib.Path) -> str:
    return path.relative_to(SRC_ROOT).as_posix()


def _classes(path: pathlib.Path) -> list[ast.ClassDef]:
    return [node for node in ast.walk(ImportScanner.parse(path)) if isinstance(node, ast.ClassDef)]


def _ir_class_names() -> set[str]:
    return {node.name for path in ImportScanner.python_files(_IR) for node in _classes(path)}


def test_the_canonical_ir_classes_are_defined_only_in_public_models() -> None:
    """``DocumentIR`` & co live in public_models/ir alone: a copy elsewhere is a second source of truth."""
    names = _ir_class_names()
    assert {"DocumentIR", "Block", "TableData"} <= names, "the IR package lost its canonical models"
    copies = {
        (_relative(path), node.name)
        for zone in _PRODUCT_ZONES
        for path in ImportScanner.python_files(zone)
        if _IR not in path.parents
        for node in _classes(path)
        if node.name in names
    }
    unexpected = sorted(copies - _NON_IR_NAMESAKES)
    assert not unexpected, f"IR class(es) redefined outside public_models/ir: {unexpected}"
    assert _NON_IR_NAMESAKES <= copies, "a listed namesake is gone: drop it from _NON_IR_NAMESAKES"


def test_the_view_generators_take_a_document_ir_and_return_text() -> None:
    """Every public method of a linearizer that renders takes ``ir: DocumentIR`` and returns ``str``."""
    rendering: list[str] = []
    problems: list[str] = []
    for path in ImportScanner.python_files(_LINEARIZE):
        for cls in (node for node in _classes(path) if node.name.endswith("Linearizer")):
            for method in (
                n for n in cls.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")
            ):
                params = [arg for arg in method.args.args if arg.arg != "self"]
                where = f"{path.name}:{cls.name}.{method.name}"
                rendering.append(where)
                if (
                    not params
                    or params[0].arg != "ir"
                    or ast.unparse(params[0].annotation or ast.Constant("")) != "DocumentIR"
                ):
                    problems.append(f"{where} does not take `ir: DocumentIR` first")
                if method.returns is None or ast.unparse(method.returns) != "str":
                    problems.append(f"{where} does not return str")
    assert len(rendering) >= 4, f"the generators' public surface moved: {rendering}"
    assert not problems, problems


def test_the_ir_package_imports_no_view_pipeline_or_service() -> None:
    """The IR is the lowest layer: only pydantic/stdlib and its own siblings."""
    foreign = sorted(
        f"{_relative(path)} -> {ref.module}"
        for path in ImportScanner.python_files(_IR)
        for ref in ImportScanner.imports_of(path)
        if not ref.level and ref.module.split(".")[0] not in _IR_ALLOWED_ROOTS
    )
    assert not foreign, f"public_models/ir must stay self-contained: {foreign}"


def test_the_view_generators_depend_on_the_public_models_only() -> None:
    """A generator reads the IR and writes a string: no store, no façade, no pipeline machinery."""
    foreign = sorted(
        f"{_relative(path)} -> {ref.module}"
        for path in ImportScanner.python_files(_LINEARIZE)
        for ref in ImportScanner.imports_of(path)
        if not ref.level
        and ref.module.split(".")[0] not in _LINEARIZE_ALLOWED_ROOTS
        and not ImportScanner.under(ref.module, "shared_libs.public_models")
    )
    assert not foreign, f"a view generator imports something besides the IR models: {foreign}"


def test_only_the_explorer_read_endpoint_consumes_the_view_generators() -> None:
    """No worker, façade or node can take a rendered view in, hence none can persist one as the IR."""
    consumers = {
        _relative(path)
        for zone in _PRODUCT_ZONES
        for path in ImportScanner.python_files(zone)
        if _LINEARIZE not in path.parents
        for ref in ImportScanner.imports_of(path)
        if not ref.level and ImportScanner.under(ref.module, _LINEARIZE_MODULE)
    }
    assert consumers == _VIEW_CONSUMERS, (
        f"view-generator importers are {sorted(consumers)}, expected {sorted(_VIEW_CONSUMERS)}: a new "
        "consumer must prove it never writes the rendered string back as the IR."
    )


def _stored_view_columns() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in ImportScanner.python_files(_TABLES):
        for node in ast.walk(ImportScanner.parse(path)):
            targets = (
                [node.target] if isinstance(node, ast.AnnAssign) else getattr(node, "targets", [])
            )
            found.update(
                (_relative(path), target.id)
                for target in targets
                if isinstance(target, ast.Name)
                and any(word in target.id.lower() for word in _STORED_VIEW_WORDS)
            )
    return found


def test_no_new_table_column_stores_a_rendered_view() -> None:
    """The persisted document content is the IR rows: no NEW column named like a stored view."""
    new = sorted(_stored_view_columns() - _STORED_VIEW_COLUMNS)
    assert not new, f"a table column looks like a persisted rendered view: {new}"
    assert _STORED_VIEW_COLUMNS <= _stored_view_columns(), (
        "a listed column is gone: drop it from the allowlist"
    )


def test_ingest_never_persists_a_rendered_table_view() -> None:
    """The only pre-existing view column (``block_table.linearized_md``) is never filled by ingest: the
    translator that persists a parsed IR writes ``None``; only the restore of an exported bundle copies
    the value it exported (itself always ``None`` from ingest)."""
    writers: dict[str, list[ast.expr]] = {}
    for zone in _PRODUCT_ZONES:
        for path in ImportScanner.python_files(zone):
            for node in ast.walk(ImportScanner.parse(path)):
                if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("BlockTable"):
                    writers.setdefault(_relative(path), []).extend(
                        kw.value for kw in node.keywords if kw.arg == "linearized_md"
                    )
    assert set(writers) == set(_BLOCK_TABLE_WRITERS), (
        f"BlockTable writers changed: {sorted(writers)}"
    )
    for file, values in writers.items():
        assert values, f"{file} builds a BlockTable without linearized_md"
        if _BLOCK_TABLE_WRITERS[file] == "none":
            assert all(isinstance(v, ast.Constant) and v.value is None for v in values), (
                f"{file} must persist linearized_md=None: the IR is canonical, a rendered view is never stored"
            )
