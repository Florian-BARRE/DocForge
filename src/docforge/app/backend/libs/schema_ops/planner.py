# ====== Code Summary ======
# SchemaOpsPlanner — resolves a PATCH's schema intent into ONE SchemaPlan. ``field_ops`` are applied
# in order to a working copy of the current schema (each field remembers the current name it came
# from, so rename chains collapse to one in-place rename); the legacy full ``fields`` list becomes a
# plan whose omitted fields are removed. Pure — no store access; invalid ops raise SchemaOpsError.

# ====== Standard Library Imports ======
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus
from pydantic import ValidationError

# ====== Local Project Imports ======
from .errors import SchemaOpsError
from .field_spec import FieldSpecModel
from .ops import AddFieldOp, FieldOp, RemoveFieldOp, RenameFieldOp, UpdateFieldOp
from .plan import SchemaPlan

# Working entry: (the CURRENT name this field came from — None for an added field, its spec).
_Entry = tuple[str | None, FieldSpecModel]


class SchemaOpsPlanner:
    """Static resolver of a schema change (field_ops or legacy full list) into a SchemaPlan."""

    logger = loggerplusplus.bind(identifier="SchemaOpsPlanner")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SchemaOpsPlanner is a static-only class and cannot be instantiated.")

    @staticmethod
    def _existing(working: dict[str, _Entry], name: str, index: int, op: str) -> _Entry:
        """Return the working entry for ``name`` or raise naming the faulty op."""
        if name not in working:
            raise SchemaOpsError(
                f"field_ops[{index}] ({op}): unknown field '{name}' — existing: {sorted(working)}."
            )
        return working[name]

    @classmethod
    def _apply(cls, working: dict[str, _Entry], dropped: set[str], op: FieldOp, index: int) -> None:
        """Apply one op to the working schema (mutates ``working`` / ``dropped``)."""
        # 1. add — a brand-new name (never one removed in this same request: use update instead).
        if isinstance(op, AddFieldOp):
            name = op.field.field_name
            if name in working:
                raise SchemaOpsError(f"field_ops[{index}] (add): field '{name}' already exists.")
            if name in dropped:
                raise SchemaOpsError(
                    f"field_ops[{index}] (add): '{name}' was removed earlier in this request — "
                    f"use an 'update' op to change a field in place (keeps its values)."
                )
            working[name] = (None, op.field)
        # 2. update — merge only the attributes sent, re-validated as a full field.
        elif isinstance(op, UpdateFieldOp):
            origin, spec = cls._existing(working, op.field_name, index, "update")
            merged = {**spec.model_dump(), **op.changes.model_dump(exclude_unset=True)}
            try:
                working[op.field_name] = (origin, FieldSpecModel.model_validate(merged))
            except ValidationError as exc:
                raise SchemaOpsError(f"field_ops[{index}] (update): {exc}") from exc
        # 3. remove — its values go with it.
        elif isinstance(op, RemoveFieldOp):
            origin, _ = cls._existing(working, op.field_name, index, "remove")
            del working[op.field_name]
            dropped.add(op.field_name)
        # 4. rename — same entry (same origin → same row, values kept) under a new name.
        elif isinstance(op, RenameFieldOp):
            origin, spec = cls._existing(working, op.field_name, index, "rename")
            if op.new_name in working:
                raise SchemaOpsError(
                    f"field_ops[{index}] (rename): '{op.new_name}' already exists."
                )
            del working[op.field_name]
            working[op.new_name] = (origin, spec.model_copy(update={"field_name": op.new_name}))

    @classmethod
    def from_ops(cls, current: Sequence[FieldSpecModel], ops: Sequence[FieldOp]) -> SchemaPlan:
        """
        Apply ``field_ops`` in order to the current schema and resolve the resulting plan.

        Args:
            current (Sequence[FieldSpecModel]): The stored schema.
            ops (Sequence[FieldOp]): The ordered operations.

        Returns:
            SchemaPlan: The target schema + collapsed renames + removed current names.

        Raises:
            SchemaOpsError: On an unknown name, a duplicate add or a rename collision.
        """
        # 1. Run every op on a working copy keyed by name, each entry remembering its origin.
        working: dict[str, _Entry] = {spec.field_name: (spec.field_name, spec) for spec in current}
        dropped: set[str] = set()
        for index, op in enumerate(ops):
            cls._apply(working, dropped, op, index)

        # 2. Collapse: a surviving origin under another name is a rename; a lost origin a removal.
        renames = {
            origin: name
            for name, (origin, _) in working.items()
            if origin is not None and origin != name
        }
        surviving = {origin for origin, _ in working.values() if origin is not None}
        removed = [spec.field_name for spec in current if spec.field_name not in surviving]
        return SchemaPlan(
            target=[spec for _, spec in working.values()], renames=renames, removed=removed
        )

    @staticmethod
    def from_fields(
        current: Sequence[FieldSpecModel], fields: Sequence[FieldSpecModel]
    ) -> SchemaPlan:
        """
        Resolve the legacy full TARGET list: matched by name, an omitted current field is removed.

        Args:
            current (Sequence[FieldSpecModel]): The stored schema.
            fields (Sequence[FieldSpecModel]): The desired full schema.

        Returns:
            SchemaPlan: The target schema, no renames, the removed current names.
        """
        # 1. A legacy list cannot express a rename — a changed name is a remove + add.
        wanted = {spec.field_name for spec in fields}
        removed = [spec.field_name for spec in current if spec.field_name not in wanted]
        return SchemaPlan(target=list(fields), removed=removed)


__all__ = ["SchemaOpsPlanner"]
