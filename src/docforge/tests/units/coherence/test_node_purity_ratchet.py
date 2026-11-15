# ====== Code Summary ======
# Node-purity ratchet. docs/architecture.md §3/§4: a pipeline node is PURE — ``Config`` + Consume ->
# Produce, no DB/S3/vector-store I/O, no process-environment or global-config read; persistence
# happens in the worker through the façades. This AST-scans every module under the three node trees
# (``pipelines/nodes``, ``pipelines/ingest/nodes``, ``pipelines/search/nodes``) and fails on a NEW
# forbidden import or use. The injected-provider network clients (httpx, openai, langchain_*) and the
# documented process-local state (client pools, the docling parse subprocess + its temp file) are NOT
# forbidden. It complements ``characterization/pipelines/test_import_graph.py`` (R-15), which pins the
# pipelines -> services edge package-wide (and allows ONE non-node edge, ``preview/projector.py``): this
# one pins the broader "node never reaches a store, an env var or the global config" contract.
# Today the node trees are clean, so ``_ALLOWED`` is empty: a node that really needs an exception
# adds ``(relative file, rule id)`` there WITH a comment saying why, as a deliberate decision.

# ====== Standard Library Imports ======
import ast
import pathlib

# ====== Local Project Imports ======
from .support.import_scan import SRC_ROOT, ImportScanner

_PIPELINES = SRC_ROOT / "shared" / "libs" / "pipelines"
_NODE_TREES = (
    _PIPELINES / "nodes",
    _PIPELINES / "ingest" / "nodes",
    _PIPELINES / "search" / "nodes",
)

# Imported module (or any submodule of it) -> rule id. Stores, the process config, the app/worker.
_FORBIDDEN_MODULES: dict[str, str] = {
    "shared_libs.services": "import-db-facade",
    "boto3": "import-s3-client",
    "aioboto3": "import-s3-client",
    "botocore": "import-s3-client",
    "aiobotocore": "import-s3-client",
    "qdrant_client": "import-vector-store",
    "sqlalchemy": "import-sql",
    "psycopg": "import-sql",
    "psycopg2": "import-sql",
    "asyncpg": "import-sql",
    "redis": "import-queue-store",
    "arq": "import-queue-store",
    "configplusplus": "import-config-loader",
    "config": "import-runtime-config",
    "backend": "import-app-or-worker",
    "app": "import-app-or-worker",
    "worker": "import-app-or-worker",
}
_ENV_ATTRIBUTES = frozenset({"environ", "environb", "getenv", "getenvb", "putenv"})
_FILE_WRITE_ATTRIBUTES = frozenset({"write_text", "write_bytes"})

# (file relative to src/docforge, rule id) tolerated today. EMPTY: the node trees are clean.
_ALLOWED: frozenset[tuple[str, str]] = frozenset()


class NodePurityScanner:
    """Finds the purity violations (as rule ids) of one node module's source."""

    @classmethod
    def violations(cls, source: str) -> set[str]:
        """The rule ids a module breaks: forbidden imports, config/env reads, persistence writes."""
        tree = ast.parse(source)
        found: set[str] = set()
        for ref in ImportScanner.imports_in(tree):
            if ref.level:
                continue  # a relative import stays inside the node/pipeline tree
            found.update(
                rule
                for prefix, rule in _FORBIDDEN_MODULES.items()
                if ImportScanner.under(ref.module, prefix)
            )
            if ref.module == "os" and _ENV_ATTRIBUTES.intersection(ref.names):
                found.add("use-os-environ")
        for node in ast.walk(tree):
            found.update(cls._rule_of(node))
        return found

    @staticmethod
    def _rule_of(node: ast.AST) -> set[str]:
        if isinstance(node, ast.Name) and node.id == "RUNTIME_CONFIG":
            return {"use-runtime-config"}
        if isinstance(node, ast.Attribute):
            if node.attr == "RUNTIME_CONFIG":
                return {"use-runtime-config"}
            if (
                node.attr in _ENV_ATTRIBUTES
                and isinstance(node.value, ast.Name)
                and node.value.id == "os"
            ):
                return {"use-os-environ"}
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "open":
                return {"use-builtin-open"}
            if isinstance(func, ast.Attribute) and func.attr in _FILE_WRITE_ATTRIBUTES:
                return {"use-file-write"}
        return set()


def _node_modules() -> list[pathlib.Path]:
    return [path for tree in _NODE_TREES for path in ImportScanner.python_files(tree)]


def _current_violations() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in _node_modules():
        relative = path.relative_to(SRC_ROOT).as_posix()
        found.update(
            (relative, rule)
            for rule in NodePurityScanner.violations(path.read_text(encoding="utf-8"))
        )
    return found


def test_the_node_trees_are_scanned() -> None:
    """A moved or renamed node tree must not turn the ratchet into a scan of nothing."""
    assert all(tree.is_dir() for tree in _NODE_TREES), _NODE_TREES
    assert len(_node_modules()) > 100, "the node trees hold ~270 modules; the scan lost them"


def test_no_node_touches_a_store_the_environment_or_the_global_config() -> None:
    """A node never imports a store client / the DB façade / the process config, never reads the
    environment or ``RUNTIME_CONFIG``, never writes a file: persistence and config live in the worker."""
    new = sorted(_current_violations() - _ALLOWED)
    assert not new, (
        f"Impure node code (file, rule): {new}. A node is Config + Consume -> Produce with no I/O "
        "(docs/architecture.md §3): move the access to the worker/façade and inject the value."
    )


def test_allowlist_has_no_stale_entry() -> None:
    """An allowed (file, rule) that no longer happens leaves the allowlist: the ratchet only tightens."""
    stale = sorted(_ALLOWED - _current_violations())
    assert not stale, f"_ALLOWED lists violations that no longer exist: {stale}"


def test_the_scanner_flags_each_kind_of_impurity() -> None:
    """The detector itself: one synthetic snippet per rule, and the allowed network clients pass."""
    flagged = {
        "from shared_libs.services.db import Database": "import-db-facade",
        "import boto3": "import-s3-client",
        "from qdrant_client import QdrantClient": "import-vector-store",
        "from config import RUNTIME_CONFIG": "import-runtime-config",
        "import os\nx = os.getenv('A')": "use-os-environ",
        "import os\nx = os.environ['A']": "use-os-environ",
        "from os import environ": "use-os-environ",
        "x = CONTEXT.RUNTIME_CONFIG": "use-runtime-config",
        "f = open('x', 'wb')": "use-builtin-open",
        "Path('x').write_bytes(b'')": "use-file-write",
    }
    for source, rule in flagged.items():
        assert rule in NodePurityScanner.violations(source), source
    pure = "import httpx\nimport openai\nfrom langchain_core.prompts import PromptTemplate\nimport tempfile\n"
    assert NodePurityScanner.violations(pure) == set()
