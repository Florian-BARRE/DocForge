# ====== Code Summary ======
# Shared fixtures for the units suite: the three stateless graph-design services (builder,
# validator, engine), and a session-scoped import of every node package so the NodeRegistry is
# populated exactly once. Individual test modules may still `import shared_libs.pipelines...nodes`
# themselves (Python caches the import; it is a no-op the second time) — this fixture just
# guarantees discovery has happened before any test body runs, regardless of collection order.

# ====== Standard Library Imports ======
import pathlib
import sys

# ====== Third-Party Library Imports ======
import pytest

# Registers every dedicated ingestion node + the generic capability families (ocr/vlm/llm/embed).
import shared_libs.pipelines.ingest.nodes  # noqa: E402,F401
import shared_libs.pipelines.nodes  # noqa: E402,F401
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.edit import GraphEditor
from shared_libs.pipelines.engine import FlowEngine
from shared_libs.pipelines.ingest.stages import StageCompiler
from shared_libs.pipelines.validation import GraphValidator

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def repo_root() -> pathlib.Path:
    """The docforge repository root (parent of app/, worker/, shared/, tests/)."""
    return REPO_ROOT


@pytest.fixture
def builder() -> PipelineBuilder:
    """A fresh PipelineBuilder (stateless, but a fresh instance keeps tests independent)."""
    return PipelineBuilder()


@pytest.fixture
def validator() -> GraphValidator:
    """A fresh GraphValidator."""
    return GraphValidator()


@pytest.fixture
def engine() -> FlowEngine:
    """A fresh FlowEngine."""
    return FlowEngine()


@pytest.fixture
def editor() -> GraphEditor:
    """A fresh GraphEditor."""
    return GraphEditor()


@pytest.fixture
def compiler() -> StageCompiler:
    """A fresh StageCompiler."""
    return StageCompiler()


def _worker_libs_on_path() -> None:
    """Add worker/backend/libs to sys.path (idempotent; root conftest already did this)."""
    path_str = str(REPO_ROOT / "worker" / "backend" / "libs")
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


_worker_libs_on_path()
