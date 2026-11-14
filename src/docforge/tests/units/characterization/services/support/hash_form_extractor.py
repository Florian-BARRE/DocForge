# ====== Code Summary ======
# HashFormExtractor — evaluates a pipeline-blob hashing form STRAIGHT FROM ITS SOURCE FILE, without
# importing the module that holds it. The forms live in the app router and the worker (two packages
# that both call their root ``backend`` / ``config`` and cannot be imported side by side in one
# process), and two of them are inline expressions inside a long method. Parsing the source, lifting
# the function (annotations and decorators dropped) or the ``config_hash = …`` expression, and
# running it in a bare namespace pins what the production code computes TODAY. When a refactor moves
# a form (e.g. into one shared BlobHasher), ``extract`` raises LookupError: re-point the test at the
# new home and keep the digest goldens — that is the whole point.

# ====== Standard Library Imports ======
import ast
import hashlib
import json
import pathlib
from collections.abc import Callable
from typing import Any

# ====== Third-Party Library Imports ======
from pydantic import BaseModel

#: src/docforge/ (this file is tests/units/characterization/services/support/<name>.py).
SOURCE_ROOT = pathlib.Path(__file__).resolve().parents[5]


class HashFormExtractor:
    """Lifts a hashing function or assignment expression out of a source file and runs it."""

    _NAMESPACE_BASE: dict[str, Any] = {"hashlib": hashlib, "json": json, "BaseModel": BaseModel}

    @classmethod
    def _tree(cls, relative_path: str) -> ast.Module:
        return ast.parse((SOURCE_ROOT / relative_path).read_text(encoding="utf-8"))

    @classmethod
    def function(cls, relative_path: str, qualname: str) -> Callable[..., Any]:
        """Compile the function ``qualname`` (``func`` or ``Class.func``) as a bare callable.

        Annotations, decorators and defaults' type hints are stripped so the body runs without the
        module's imports; the body itself is executed unchanged.

        Raises:
            LookupError: The function is no longer at that path / name.
        """
        scope: list[ast.stmt] = cls._tree(relative_path).body
        *classes, name = qualname.split(".")
        for class_name in classes:
            scope = next(
                (n.body for n in scope if isinstance(n, ast.ClassDef) and n.name == class_name),
                None,
            ) or cls._missing(relative_path, qualname)
        node = next(
            (n for n in scope if isinstance(n, ast.FunctionDef) and n.name == name), None
        ) or cls._missing(relative_path, qualname)
        node.decorator_list = []
        node.returns = None
        for argument in [*node.args.args, *node.args.kwonlyargs, *node.args.posonlyargs]:
            argument.annotation = None
        module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
        namespace = dict(cls._NAMESPACE_BASE)
        exec(compile(module, f"{relative_path}:{qualname}", "exec"), namespace)  # noqa: S102
        return namespace[name]

    @classmethod
    def assigned_expression(cls, relative_path: str, target: str, variables: dict[str, Any]) -> Any:
        """Evaluate the first ``<target> = <expr>`` whose expression calls ``hashlib.sha256``.

        Args:
            relative_path (str): Source file, relative to ``src/docforge``.
            target (str): The assigned variable name (``config_hash``).
            variables (dict[str, Any]): Values for the free names of the expression (``blob``).

        Raises:
            LookupError: No such assignment is left in the file.
        """
        for node in ast.walk(cls._tree(relative_path)):
            if (
                isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == target for t in node.targets)
                and "sha256" in ast.dump(node.value)
            ):
                expression = ast.fix_missing_locations(ast.Expression(body=node.value))
                code = compile(expression, f"{relative_path}:{target}", "eval")
                return eval(code, {**cls._NAMESPACE_BASE, **variables})  # noqa: S307
        cls._missing(relative_path, target)

    @staticmethod
    def _missing(relative_path: str, what: str) -> Any:
        raise LookupError(
            f"hashing form {what!r} is no longer in {relative_path}: re-point this characterization "
            "at its new home and keep the digest goldens unchanged."
        )
