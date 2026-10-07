# ====== Code Summary ======
# SchemaPlan — the resolved outcome of a schema change (legacy full list OR field_ops): the target
# schema keyed by post-change names, the in-place renames, and the removed names. The single input
# both the differ (preview) and the facade (apply) consume, so preview and apply can never disagree.

# ====== Standard Library Imports ======
from dataclasses import dataclass, field

# ====== Local Project Imports ======
from .field_spec import FieldSpecModel


@dataclass(slots=True)
class SchemaPlan:
    """
    A resolved metadata-schema change.

    Attributes:
        target (list[FieldSpecModel]): The full post-change schema (post-rename names).
        renames (dict[str, str]): Current name → new name (values kept; applied as an UPDATE).
        removed (list[str]): Current names deleted (their values cascade away).
    """

    target: list[FieldSpecModel]
    renames: dict[str, str] = field(default_factory=dict)
    removed: list[str] = field(default_factory=list)


__all__ = ["SchemaPlan"]
