# ====== Code Summary ======
# DefaultTargetCorrection — the target-less (default) search's guard against a content sparse vector
# encoded by ANOTHER sparse provider than the configured one (its IDF modifier disagrees with the
# config-derived layout — e.g. a bm25_local store under a bge_server config). Querying it would score
# the query with the wrong encoder, so the lexical axis is DROPPED: the default search falls back to
# content-dense only (or answers empty on a sparse-only collection), with a hint naming the fix
# (rebuild_index). Never a 422 — a plain query must keep working while the store is repaired.

# ====== Standard Library Imports ======
import uuid
from dataclasses import dataclass, field

# ====== Internal Project Imports ======
from shared_libs.public_models import VectorLayout
from shared_libs.public_models.search.target import CONTENT_FIELD, SearchTarget
from shared_libs.services.db.qdrant import VectorNames

# ====== Local Project Imports ======
from .declared_cache import DeclaredLoader, DeclaredVectorsCache
from .filter_hint import FilterHint

LEXICAL_DISABLED_MESSAGE = (
    "lexical axis disabled: the stored sparse vectors were encoded with a different sparse "
    "provider — run rebuild_index"
)


@dataclass(frozen=True, slots=True)
class DefaultTargetPlan:
    """What the default search should run.

    Attributes:
        targets (list[SearchTarget] | None): The targets to search (None = the stock default).
        empty (bool): True when nothing searchable is left (answer with no hits, no spend).
        hints (list[FilterHint]): The explanation to surface when the lexical axis was dropped.
    """

    targets: list[SearchTarget] | None = None
    empty: bool = False
    hints: list[FilterHint] = field(default_factory=list)


class DefaultTargetCorrection:
    """Decides the default search's targets against the store's declared sparse modifier."""

    def __init__(self, cache: DeclaredVectorsCache) -> None:
        """
        Args:
            cache (DeclaredVectorsCache): The short-TTL declared-vectors cache.
        """
        self._cache = cache

    async def plan(
        self,
        collection_id: uuid.UUID,
        targets: list[SearchTarget] | None,
        layout: VectorLayout,
        loader: DeclaredLoader,
    ) -> DefaultTargetPlan:
        """
        The default search plan — unchanged unless the content sparse vector is mismatched.

        Args:
            collection_id (uuid.UUID): The searched collection.
            targets (list[SearchTarget] | None): The request's targets (only None/empty is corrected;
                explicit targets are gated by the target validator).
            layout (VectorLayout): The config-derived vector layout.
            loader (DeclaredLoader): The store read behind the cache.

        Returns:
            DefaultTargetPlan: The targets to run, or an empty answer, plus the hint.
        """
        # 1. Explicit targets, or no sparse axis configured: nothing to correct (no store read).
        if targets or not layout.sparse:
            return DefaultTargetPlan(targets=targets)
        # 2. The content sparse vector carries the configured modifier → the stock default holds.
        declared = await self._cache.get(collection_id, loader)
        if declared is None or VectorNames.CONTENT_SPARSE not in declared.mismatched(layout):
            return DefaultTargetPlan(targets=targets)
        # 3. Mismatched: drop the lexical axis — dense-only when there is one, else nothing to search.
        hint = FilterHint(field=CONTENT_FIELD, value=None, message=LEXICAL_DISABLED_MESSAGE)
        if layout.dense:
            dense_only = [SearchTarget(field=CONTENT_FIELD, semantic=True, lexical=False)]
            return DefaultTargetPlan(targets=dense_only, hints=[hint])
        return DefaultTargetPlan(empty=True, hints=[hint])


__all__ = ["DefaultTargetCorrection", "DefaultTargetPlan", "LEXICAL_DISABLED_MESSAGE"]
