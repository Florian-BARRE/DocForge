# ====== Code Summary ======
# CollectionSchemaPatch — resolves the schema part of a collection PATCH (legacy ``fields`` or
# ``field_ops``) into the plan the facade applies, the ORM rows, and the SchemaDiff the response
# reports, with every rejection a 422 BEFORE any write (so dry_run and apply validate identically).
# Kept out of router.py so the route stays orchestration.

# ====== Standard Library Imports ======
from dataclasses import dataclass

# ====== Third-Party Library Imports ======
from fastapi import HTTPException

# ====== Internal Project Imports ======
from shared_libs.services.db.facades import DatabaseHelpers
from shared_libs.services.db.postgresql.tables import Collection, MetadataField

# ====== Local Project Imports ======
from ...context import CONTEXT
from ...libs.schema_ops import (
    FieldSpecModel,
    SchemaDiff,
    SchemaDiffer,
    SchemaOpsError,
    SchemaOpsPlanner,
    SchemaPlan,
)
from .helpers import CollectionHelpers
from .models import UpdateCollectionRequest


@dataclass(slots=True)
class ResolvedSchemaPatch:
    """
    The validated schema part of a PATCH.

    Attributes:
        plan (SchemaPlan): Target schema + renames + removed names.
        rows (list[MetadataField]): The target schema as ORM rows (what the facade diffs against).
        diff (SchemaDiff): What the change does (reported on the response).
    """

    plan: SchemaPlan
    rows: list[MetadataField]
    diff: SchemaDiff

    @property
    def departed(self) -> list[str]:
        """
        Names that truly leave the schema — removed or renamed away AND not reused by the target.

        A name that is back in the post-change schema (a swap A↔B, a remove A + rename B→A, a
        rename A→B + add A) is LIVE: purging it would blank its filter on every point until the
        backfill repaints. It is left in place; the convergent backfill repaints (and clears for
        documents without a value) the footprint of its new owner.
        """
        reused = {spec.field_name for spec in self.plan.target}
        return [name for name in (*self.plan.removed, *self.plan.renames) if name not in reused]


class CollectionSchemaPatch:
    """Static resolver of a PATCH's schema intent into a validated plan + rows + diff."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("CollectionSchemaPatch is a static-only class and cannot be instantiated.")

    @staticmethod
    def _plan(current: list[FieldSpecModel], request: UpdateCollectionRequest) -> SchemaPlan:
        """Build the plan from whichever schema surface the request carries (422 on a bad op)."""
        try:
            if request.field_ops is not None:
                return SchemaOpsPlanner.from_ops(current, request.field_ops)
            return SchemaOpsPlanner.from_fields(current, request.fields or [])
        except SchemaOpsError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @classmethod
    async def resolve(
        cls, collection: Collection, request: UpdateCollectionRequest
    ) -> ResolvedSchemaPatch | None:
        """
        Resolve and fully validate the schema part of a PATCH (None when it does not touch it).

        Args:
            collection (Collection): The stored collection.
            request (UpdateCollectionRequest): The PATCH body.

        Returns:
            ResolvedSchemaPatch | None: The plan, its rows and its diff; None without a schema part.

        Raises:
            HTTPException: 422 on a bad op, a bad field, or colliding vector slugs.
        """
        # 1. No schema surface in the body → nothing to resolve.
        if request.fields is None and request.field_ops is None:
            return None

        # 2. Plan against the stored schema, then the SAME per-field guards a create/legacy PATCH runs.
        stored = await CONTEXT.database.collections.get_schema(collection.id)
        current = CollectionHelpers.to_field_specs(stored)
        plan = cls._plan(current, request)
        CollectionHelpers.validate_fields(plan.target)
        rows = CollectionHelpers.to_field_rows(plan.target)
        try:
            DatabaseHelpers.validate_vector_slugs(rows)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        # 3. Measure what the removals destroy and describe the change.
        lost = await CONTEXT.database.schema_changes.count_field_values(collection.id, plan.removed)
        diff = SchemaDiffer.build(
            current, plan, lost, indexed=getattr(collection, "indexed_signature", None) is not None
        )
        return ResolvedSchemaPatch(plan=plan, rows=rows, diff=diff)


__all__ = ["CollectionSchemaPatch", "ResolvedSchemaPatch"]
