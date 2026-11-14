# ====== Code Summary ======
# FacadeSurfaceReader — reads the PUBLIC surface of a facade object as stable text lines, one per
# public callable: ``<kind> <name><signature>`` with kind in {async, asyncgen, sync}. Annotation and
# default-value dotted paths are reduced to their last component (``datetime.datetime`` ->
# ``datetime``, ``shared_libs.….Document`` -> ``Document``) so moving a table or model module does
# not churn the surface, while a renamed / re-signed / sync<->async method does.

# ====== Standard Library Imports ======
import inspect
import re
from typing import Any


class FacadeSurfaceReader:
    """Turns a facade instance into its public-callable surface lines."""

    _DOTTED_PATH = re.compile(r"\b(?:[A-Za-z_][A-Za-z0-9_]*\.)+(?=[A-Za-z_])")

    @classmethod
    def kind_of(cls, member: Any) -> str:
        """``asyncgen`` / ``async`` / ``sync`` for a callable member."""
        if inspect.isasyncgenfunction(member):
            return "asyncgen"
        if inspect.iscoroutinefunction(member):
            return "async"
        return "sync"

    @classmethod
    def normalise(cls, signature: str) -> str:
        """Drop the module path of every dotted name in a rendered signature."""
        return cls._DOTTED_PATH.sub("", signature)

    @classmethod
    def lines_of(cls, facade: object) -> tuple[str, ...]:
        """The sorted surface lines of ``facade``'s public callables (underscore names excluded)."""
        lines = []
        for name in sorted(dir(facade)):
            if name.startswith("_"):
                continue
            member = getattr(facade, name)
            if not callable(member):
                continue
            signature = cls.normalise(str(inspect.signature(member)))
            lines.append(f"{cls.kind_of(member)} {name}{signature}")
        return tuple(lines)

    @classmethod
    def surface_of(cls, database: object, attribute_names: tuple[str, ...]) -> dict[str, tuple]:
        """``{attribute: (facade class name, surface lines)}`` for the named Database attributes."""
        return {
            name: (type(getattr(database, name)).__name__, cls.lines_of(getattr(database, name)))
            for name in attribute_names
        }
