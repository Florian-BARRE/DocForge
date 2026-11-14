# ====== Code Summary ======
# Loaders for the two modules the queue/cron characterization tests read WITHOUT importing the app/worker
# ``config`` and ``backend`` packages (both apps define top-level ``config`` and ``backend`` packages, so
# importing either for real would collide inside one pytest session):
#   - ``WorkerAppLoader.load_worker_app`` executes the REAL ``worker/backend/app.py`` under a stub
#     package, with ``config.RUNTIME_CONFIG`` replaced by the worker's DEFAULT values — read statically
#     (AST) from ``worker/config/runtime_config.py``, so neither the environment nor a local ``.env``
#     can shift them, and a changed default shows up in the golden.
#   - ``WorkerAppLoader.load_queue_client`` executes the REAL ``app/backend/utils/queue.py`` by path.
# Test support only: no production file is touched.

# ====== Standard Library Imports ======
import ast
import importlib.util
import pathlib
import sys
import types
from typing import Any

_DOCFORGE_ROOT = pathlib.Path(__file__).resolve().parents[4]
_WORKER_APP = _DOCFORGE_ROOT / "worker" / "backend" / "app.py"
_WORKER_CONFIG = _DOCFORGE_ROOT / "worker" / "config" / "runtime_config.py"
_QUEUE_CLIENT = _DOCFORGE_ROOT / "app" / "backend" / "utils" / "queue.py"

_STUB_PACKAGE = "characterization_worker_backend"


class WorkerAppLoader:
    """Static-only: load the worker factory and the queue client for a characterization test."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("WorkerAppLoader is a static-only class and cannot be instantiated.")

    @staticmethod
    def worker_config_defaults() -> dict[str, Any]:
        """
        Every ``NAME = env("NAME", ..., default=<literal>)`` of the worker's RUNTIME_CONFIG, by name.

        Returns:
            dict[str, Any]: ``{NAME: default}`` — only the variables whose default is a literal.
        """
        tree = ast.parse(_WORKER_CONFIG.read_text(encoding="utf-8"))
        config_class = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "RUNTIME_CONFIG"
        )
        defaults: dict[str, Any] = {}
        for node in config_class.body:
            if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
                continue
            call = node.value
            if not (isinstance(call.func, ast.Name) and call.func.id == "env"):
                continue
            for keyword in call.keywords:
                if keyword.arg == "default":
                    try:
                        defaults[node.targets[0].id] = ast.literal_eval(keyword.value)
                    except ValueError:
                        pass
        return defaults

    @classmethod
    def load_worker_app(cls, monkeypatch: Any, jobs_package: Any, **overrides: Any) -> Any:
        """
        Execute the real ``worker/backend/app.py`` and return its module.

        Args:
            monkeypatch (Any): The pytest monkeypatch (sys.modules entries are undone at teardown).
            jobs_package (Any): The worker's already-imported flat ``jobs`` package.
            **overrides (Any): RUNTIME_CONFIG values replacing the defaults (e.g. a retention window).

        Returns:
            Any: The executed module; ``create_worker_settings()`` builds the arq WorkerSettings.
        """
        config = types.SimpleNamespace(
            **{"REDIS_URL": "redis://localhost:6379", **cls.worker_config_defaults(), **overrides}
        )
        config_module = types.ModuleType("config")
        config_module.RUNTIME_CONFIG = config
        lifespan_module = types.ModuleType(f"{_STUB_PACKAGE}.lifespan")
        lifespan_module.startup = _startup_stub
        lifespan_module.shutdown = _shutdown_stub
        package = types.ModuleType(_STUB_PACKAGE)
        package.__path__ = []
        libs_package = types.ModuleType(f"{_STUB_PACKAGE}.libs")
        libs_package.__path__ = []
        monkeypatch.setitem(sys.modules, "config", config_module)
        monkeypatch.setitem(sys.modules, _STUB_PACKAGE, package)
        monkeypatch.setitem(sys.modules, f"{_STUB_PACKAGE}.libs", libs_package)
        monkeypatch.setitem(sys.modules, f"{_STUB_PACKAGE}.libs.jobs", jobs_package)
        monkeypatch.setitem(sys.modules, f"{_STUB_PACKAGE}.lifespan", lifespan_module)
        return cls._execute(f"{_STUB_PACKAGE}.app", _WORKER_APP)

    @classmethod
    def load_queue_client(cls) -> Any:
        """Execute the real ``app/backend/utils/queue.py`` by path and return its ``QueueClient`` class."""
        return cls._execute("characterization_queue_client", _QUEUE_CLIENT).QueueClient

    @staticmethod
    def _execute(module_name: str, path: pathlib.Path) -> Any:
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


async def _startup_stub(ctx: dict) -> None:
    """Stand-in for the worker's ``on_startup`` hook (never run here)."""


async def _shutdown_stub(ctx: dict) -> None:
    """Stand-in for the worker's ``on_shutdown`` hook (never run here)."""
