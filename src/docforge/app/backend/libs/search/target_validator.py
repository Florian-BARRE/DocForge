# ====== Code Summary ======
# SearchTargetValidator — the pure pre-spend 422 gate over a request's search targets: each target
# must name content or a known field, select a modality, and only ask for vectors actually indexed —
# both flagged in the Postgres schema AND declared by the Qdrant store (a field toggled semantic/lexical
# after first ingest has the flag but no vector until the index is rebuilt; Qdrant would otherwise
# reject the query and surface as a misleading "invalid search graph" error). The embedder's layout
# adds the axis gate: a semantic target on a sparse-only collection (or lexical on a dense-only one)
# is a 422, and a sparse vector declared for another sparse encoder (IDF modifier mismatch) is
# reported like an undeclared one, with the rebuild hint.

# ====== Standard Library Imports ======
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.public_models import VectorLayout
from shared_libs.public_models.search import CONTENT_FIELD, SearchTarget
from shared_libs.services.db.postgresql.tables import MetadataField
from shared_libs.services.db.qdrant import DeclaredVectors, VectorNames

# The remediation a caller is pointed to when the store lacks a flagged field's named vector.
_REBUILD_HINT = (
    "the vector store has not declared it yet (Qdrant cannot add a named vector to a live "
    "collection) — the collection's index must be rebuilt (rebuild_index: "
    "POST /api/v1/collections/{collection_id}/rebuild-index) before it is searchable"
)


class SearchTargetValidator:
    """Static validation of requested search targets against the indexed vectors."""

    logger = loggerplusplus.bind(identifier="SearchTargetValidator")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SearchTargetValidator is a static-only class and cannot be instantiated.")

    @staticmethod
    def _undeclared(
        field: str,
        semantic: bool,
        declared: DeclaredVectors | None,
        layout: VectorLayout | None,
    ) -> str | None:
        """Return the store error for one modality of a target, or None when it is queryable.

        A sparse vector declared under the other IDF modifier holds another sparse encoder's vectors
        (it no longer matches the configured provider) — it is as unqueryable as an undeclared one.
        """
        # 1. No space yet (never ingested) → nothing is declared nor searchable; nothing to report.
        if declared is None:
            return None
        # 2. The named vector the read side would query for this modality must exist in the store.
        label = "content" if field == CONTENT_FIELD else f"field '{field}'"
        if semantic:
            name = (
                VectorNames.CONTENT_DENSE
                if field == CONTENT_FIELD
                else VectorNames.field_dense(field)
            )
            if name not in declared.dense:
                return f"{label} has no indexed semantic vector — {_REBUILD_HINT}"
            return None
        name = (
            VectorNames.CONTENT_SPARSE
            if field == CONTENT_FIELD
            else VectorNames.field_sparse(field)
        )
        mismatched = layout is not None and name in declared.mismatched(layout)
        if name not in declared.sparse or mismatched:
            return f"{label} has no indexed lexical vector — {_REBUILD_HINT}"
        return None

    @staticmethod
    def _axis_error(target: SearchTarget, layout: VectorLayout | None) -> list[str]:
        """The 422 errors of a modality the collection's embedder has no provider for."""
        if layout is None:
            return []
        errors = []
        if target.semantic and not layout.dense:
            errors.append(
                f"target '{target.field}' asks for a semantic search but the collection's embedder "
                "has no dense provider (sparse-only) — search it lexically"
            )
        if target.lexical and not layout.sparse:
            errors.append(
                f"target '{target.field}' asks for a lexical search but the collection's embedder "
                "has no sparse provider (dense-only) — search it semantically"
            )
        return errors

    @staticmethod
    def needs_store_check(search_in: Sequence[SearchTarget] | None) -> bool:
        """Whether the targets need the store's declarations: a metadata field, or any lexical
        target (its sparse vector may be declared for another sparse encoder)."""
        return any(t.field != CONTENT_FIELD or t.lexical for t in search_in or ())

    @classmethod
    def validate_search_targets(
        cls,
        search_in: Sequence[SearchTarget] | None,
        schema: Sequence[MetadataField],
        declared: DeclaredVectors | tuple[set[str], set[str]] | None = None,
        layout: VectorLayout | None = None,
    ) -> list[str]:
        """
        Validate the requested search targets against the collection's indexed vectors.

        A target may name ``"content"`` or a metadata field; a modality is only valid when the
        embedder has that axis (layout) and the vector was actually indexed for it (semantic → dense,
        lexical → bm25, declared by the store under the configured sparse modifier). A target asking
        for a vector that was never indexed, or a selection with no modality at all, is a caller
        error the route rejects 422 BEFORE any spend.

        Args:
            search_in (Sequence[SearchTarget] | None): The requested targets (None = default path).
            schema (Sequence[MetadataField]): The collection's metadata schema.
            declared (DeclaredVectors | tuple | None): What the Qdrant store declares (a legacy
                ``(dense, sparse)`` pair is accepted); None when it has no space yet (or the caller
                skipped the store read).
            layout (VectorLayout | None): The embedder's config-derived layout (None = unchecked).

        Returns:
            list[str]: Human-readable error messages (empty when the selection is valid). None
            search_in yields no errors (the default content path is shaped by the search blob).
        """
        if isinstance(declared, tuple):
            declared = DeclaredVectors(dense=frozenset(declared[0]), sparse=frozenset(declared[1]))
        # 1. None → the default content path, always valid; nothing to check.
        if search_in is None:
            return []

        # 2. The three surfaces a target may legitimately name.
        known = {row.field_name for row in schema}
        semantic = {row.field_name for row in schema if row.semantic}
        lexical = {row.field_name for row in schema if row.lexical}

        # 3. Every target must resolve to at least one indexed vector; the whole set must select one.
        errors: list[str] = []
        any_modality = False
        for target in search_in:
            is_content = target.field == CONTENT_FIELD
            if not is_content and target.field not in known:
                errors.append(f"unknown field '{target.field}'")
                continue
            if not target.semantic and not target.lexical:
                errors.append(f"target '{target.field}' selects no modality (semantic or lexical)")
                continue
            any_modality = True
            axis_errors = cls._axis_error(target, layout)
            if axis_errors:
                errors.extend(axis_errors)
                continue
            if target.semantic:
                if not is_content and target.field not in semantic:
                    errors.append(f"field '{target.field}' has no semantic (dense) vector")
                else:
                    errors.extend(
                        filter(None, [cls._undeclared(target.field, True, declared, layout)])
                    )
            if target.lexical:
                if not is_content and target.field not in lexical:
                    errors.append(f"field '{target.field}' has no lexical (bm25) vector")
                else:
                    errors.extend(
                        filter(None, [cls._undeclared(target.field, False, declared, layout)])
                    )
        if not any_modality:
            errors.append("select at least one modality (semantic or lexical) to search")
        return errors


__all__ = ["SearchTargetValidator"]
