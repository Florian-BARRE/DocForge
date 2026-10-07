# ====== Code Summary ======
# SearchModelMapper — maps search-library values onto the route's wire models and back: a graph Hit
# into its flat client hit, a FilterHint into its client hint, the request's target models into the
# public SearchTarget artefacts, and a 0-based page index into the 1-based page number a reader cites.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.public_models.search import Hit, SearchTarget

# ====== Local Project Imports ======
from ...libs.search import FilterHint
from .models import BlockLocationModel, SearchHint, SearchHitModel, SearchTargetModel


class SearchModelMapper:
    """Static mapping between search-library values and the route's wire models."""

    logger = loggerplusplus.bind(identifier="SearchModelMapper")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SearchModelMapper is a static-only class and cannot be instantiated.")

    @staticmethod
    def page_number(page: int | None) -> int | None:
        """Convert a stored 0-based page index into the 1-based page number a reader cites."""
        # 1. None (page-less) stays None; a real index — including 0 — shifts by one.
        return page + 1 if page is not None else None

    @staticmethod
    def to_hit_model(hit: Hit) -> SearchHitModel:
        """
        Flatten a graph Hit (the search pipeline's terminal unit) into its client model.

        The graph's Hit carries the ranking fields directly (chunk_id, document_id, score, text);
        chunk_index and token_count ride along in ``Hit.metadata`` (the read port hydrates them
        there), so they are lifted out here into the flat client shape.

        Args:
            hit (Hit): One hydrated, ranked hit produced by the search pipeline.

        Returns:
            SearchHitModel: The flat, client-facing view of the hit.
        """
        # 1. chunk_index/token_count + source identity/metadata + block location live in the
        #    hydrated metadata bag (never on the Hit's spine) — the read port fills them so the hit
        #    self-cites (which section, which document, and WHERE on the page).
        metadata = hit.metadata or {}
        return SearchHitModel(
            chunk_id=hit.chunk_id,
            document_id=hit.document_id,
            filename=metadata.get("filename"),
            document_title=metadata.get("document_title"),
            heading_path=metadata.get("heading_path") or [],
            metadata=metadata.get("document_metadata") or {},
            score=hit.score,
            text=hit.text or "",
            chunk_index=metadata.get("chunk_index", 0),
            token_count=metadata.get("token_count", 0),
            block_ids=metadata.get("block_ids") or [],
            page=metadata.get("page"),
            page_number=SearchModelMapper.page_number(metadata.get("page")),
            bbox=metadata.get("bbox"),
            block_locations=[
                BlockLocationModel(
                    page=loc["page"],
                    page_number=SearchModelMapper.page_number(loc["page"]),
                    bbox=loc["bbox"],
                )
                for loc in (metadata.get("block_locations") or [])
            ],
        )

    @staticmethod
    def to_hint_model(hint: FilterHint) -> SearchHint:
        """
        Map a resolver/zero-hit FilterHint onto its client model.

        Args:
            hint (FilterHint): The library-side hint.

        Returns:
            SearchHint: The client-facing hint.
        """
        # 1. Field-for-field copy (the client model is the wire contract).
        return SearchHint(
            field=hint.field,
            value=hint.value,
            message=hint.message,
            suggestions=list(hint.suggestions),
        )

    @staticmethod
    def to_search_targets(
        search_in: list[SearchTargetModel] | None,
    ) -> list[SearchTarget] | None:
        """
        Map the request's search-target models to the public SearchTarget artefacts (or None).

        Args:
            search_in (list[SearchTargetModel] | None): The requested targets (None passed through).

        Returns:
            list[SearchTarget] | None: The public targets, or None to let the default apply.
        """
        # 1. None rides through so the service applies the content default (unchanged behaviour).
        if search_in is None:
            return None
        # 2. One public target per requested model (validated already by the route).
        return [
            SearchTarget(field=t.field, semantic=t.semantic, lexical=t.lexical) for t in search_in
        ]


__all__ = ["SearchModelMapper"]
