# ====== Code Summary ======
# Helper for the model/resource sub-packages created by splitting an oversized module. The split
# classes live in sub-modules, but their public identity — ``cls.__module__``, hence ``repr``, pickle
# and every snapshot of the surface — must stay the one they had as a single module. The package
# ``__init__`` calls ``pin_module_path`` once, after its re-exports, to restore it.

# ====== Standard Library Imports ======
from collections.abc import Iterable, MutableMapping
from typing import Any


def pin_module_path(
    package: str, namespace: MutableMapping[str, Any], names: Iterable[str]
) -> None:
    """
    Make re-exported classes report the package path they were importable from before the split.

    Only a class defined in a sub-module of ``package`` is touched; constants, aliases and classes
    that already live at the package level are left alone.

    Args:
        package (str): The dotted package path (``__name__`` of the package's ``__init__``).
        namespace (MutableMapping[str, Any]): The package's namespace (``globals()``).
        names (Iterable[str]): The exported names (the package's ``__all__``).
    """
    prefix = f"{package}."
    for name in names:
        exported = namespace[name]
        if isinstance(exported, type) and exported.__module__.startswith(prefix):
            exported.__module__ = package
