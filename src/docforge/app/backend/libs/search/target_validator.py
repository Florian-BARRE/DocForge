# ====== Code Summary ======
# SearchTargetValidator — the pure pre-spend 422 gate over a request's search targets: each target
# must name content or a known field, select a modality, and only ask for vectors actually indexed.

# ====== Standard Library Imports ======
from collections.abc import Sequence

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.public_models.search import CONTENT_FIELD, SearchTarget
from shared_libs.services.db.postgresql.tables import MetadataField


class SearchTargetValidator:
    """Static validation of requested search targets against the indexed vectors."""

    logger = loggerplusplus.bind(identifier="SearchTargetValidator")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SearchTargetValidator is a static-only class and cannot be instantiated.")

    @staticmethod
    def validate_search_targets(
        search_in: Sequence[SearchTarget] | None, schema: Sequence[MetadataField]
    ) -> list[str]:
        """
        Validate the requested search targets against the collection's indexed vectors.

        A target may name ``"content"`` (always both modalities) or a metadata field; a modality is
        only valid when that field was actually indexed for it (semantic → dense, lexical → bm25).
        A target asking for a vector that was never indexed, or a selection with no modality at all,
        is a caller error the route rejects 422 BEFORE any spend.

        Args:
            search_in (Sequence[SearchTarget] | None): The requested targets (None = default path).
            schema (Sequence[MetadataField]): The collection's metadata schema.

        Returns:
            list[str]: Human-readable error messages (empty when the selection is valid). None
            search_in yields no errors (the unchanged content default is always valid).
        """
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
            if target.semantic:
                any_modality = True
                if not is_content and target.field not in semantic:
                    errors.append(f"field '{target.field}' has no semantic (dense) vector")
            if target.lexical:
                any_modality = True
                if not is_content and target.field not in lexical:
                    errors.append(f"field '{target.field}' has no lexical (bm25) vector")
        if not any_modality:
            errors.append("select at least one modality (semantic or lexical) to search")
        return errors


__all__ = ["SearchTargetValidator"]
