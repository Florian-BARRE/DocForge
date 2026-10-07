# ====== Code Summary ======
# SchemaDiffer — turns a resolved SchemaPlan (+ the stored schema, the value counts of the removed
# fields and whether the collection has an indexed baseline) into the SchemaDiff the PATCH reports.
# Pure: the same function previews a dry_run and describes an applied change.

# ====== Standard Library Imports ======
from collections.abc import Mapping, Sequence

# ====== Local Project Imports ======
from .diff_models import SchemaDiff, SchemaDiffModifiedField, SchemaDiffRename
from .field_spec import FieldSpecModel
from .plan import SchemaPlan

# Attributes whose change moves the vector surface of a searchable field (see CollectionIndexSignature).
_VECTOR_ATTRS = frozenset({"semantic", "lexical", "field_type"})


class SchemaDiffer:
    """Static builder of a SchemaDiff from a SchemaPlan."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SchemaDiffer is a static-only class and cannot be instantiated.")

    @staticmethod
    def _changed_attrs(before: FieldSpecModel, after: FieldSpecModel) -> list[str]:
        """Return the attributes (name excluded) whose value differs between two specs."""
        old = before.model_dump(exclude={"field_name"})
        new = after.model_dump(exclude={"field_name"})
        return sorted(key for key in new if new[key] != old[key])

    @staticmethod
    def _needs_reindex(spec: FieldSpecModel, changed: list[str] | None, renamed: bool) -> bool:
        """Decide whether a field's change needs a reindex (``changed`` None = newly added)."""
        searchable = spec.semantic or spec.lexical
        if not searchable:
            return False
        return changed is None or renamed or bool(_VECTOR_ATTRS.intersection(changed))

    @classmethod
    def build(
        cls,
        current: Sequence[FieldSpecModel],
        plan: SchemaPlan,
        values_lost: Mapping[str, int],
        *,
        indexed: bool,
    ) -> SchemaDiff:
        """
        Describe a schema plan against the stored schema.

        Args:
            current (Sequence[FieldSpecModel]): The stored schema.
            plan (SchemaPlan): The resolved change.
            values_lost (Mapping[str, int]): Removed field → stored value rows it destroys.
            indexed (bool): The collection has an indexed baseline (else nothing can need a reindex).

        Returns:
            SchemaDiff: added / modified / removed / renamed / values_lost / reindex_required_fields.
        """
        # 1. Map each target field back to the stored field it came from (renames resolved).
        by_name = {spec.field_name: spec for spec in current}
        origin_of = {new: old for old, new in plan.renames.items()}
        diff = SchemaDiff(
            removed=list(plan.removed),
            renamed=[SchemaDiffRename(from_name=o, to_name=n) for o, n in plan.renames.items()],
            values_lost={name: int(values_lost.get(name, 0)) for name in plan.removed},
        )

        # 2. Classify every target field: added (no origin) or modified (attrs changed). A name that is
        #    NOT a rename target only inherits the stored field of the same name when that field was
        #    neither removed nor renamed away — "rename A→B, then add a new A" makes the new A an add.
        for spec in plan.target:
            if spec.field_name in origin_of:
                origin: str | None = origin_of[spec.field_name]
            elif spec.field_name in plan.renames or spec.field_name in plan.removed:
                origin = None
            else:
                origin = spec.field_name
            before = by_name.get(origin) if origin is not None else None
            changed = None if before is None else cls._changed_attrs(before, spec)
            if changed is None:
                diff.added.append(spec.field_name)
            elif changed:
                diff.modified.append(
                    SchemaDiffModifiedField(field_name=spec.field_name, changed_attrs=changed)
                )
            if indexed and cls._needs_reindex(spec, changed, spec.field_name in origin_of):
                diff.reindex_required_fields.append(spec.field_name)
        return diff


__all__ = ["SchemaDiffer"]
