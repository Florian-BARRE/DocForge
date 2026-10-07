# ====== Code Summary ======
# ReplayGuard — the route-side fail-fast for a ``replay_from`` reingest: plans the replay on the
# collection's CURRENT (healed) pipeline with the pure ReplayPlanner and refuses an unsupported stage
# with a 422 that names WHY and lists the stages this pipeline CAN be replayed from — before any job is
# minted. The worker re-plans at run time (a pipeline edited in between fails the job, named).

# ====== Third-Party Library Imports ======
from fastapi import HTTPException

# ====== Internal Project Imports ======
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.ingest import BlobNormalizationError, BlobNormalizer
from shared_libs.pipelines.ingest.replay import ReplayPlanner, ReplayUnsupportedError
from shared_libs.services.db.postgresql.tables import Collection


class ReplayGuard:
    """Static-only: validate a requested ``replay_from`` against a collection's pipeline (422)."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ReplayGuard is a static-only class and cannot be instantiated.")

    @staticmethod
    def not_replayable(document_id: object) -> HTTPException:
        """The 422 for a document with no persisted IR to replay from."""
        return HTTPException(
            status_code=422,
            detail={
                "code": "replay_unsupported",
                "reason": f"document {document_id} has no persisted IR to replay from — run a "
                "full reingest first",
                "allowed": [],
            },
        )

    @classmethod
    def assert_replayable(cls, collection: Collection, replay_from: str | None) -> None:
        """
        Refuse (422) a ``replay_from`` the collection's pipeline cannot honour.

        Args:
            collection (Collection): The target collection (its stored pipeline is planned on).
            replay_from (str | None): The requested stage; None (a full run) always passes.

        Raises:
            HTTPException: 422 ``replay_unsupported`` with ``reason`` + the ``allowed`` stages.
        """
        # 1. A full run has nothing to check.
        if replay_from is None:
            return
        # 2. Plan on the healed pipeline; a refusal becomes a reasoned 422 listing the alternatives.
        try:
            group = PipelineBuilder().build(BlobNormalizer.normalize(collection.pipeline))
        except BlobNormalizationError as exc:
            raise HTTPException(status_code=422, detail=f"Collection {collection.id}: {exc}")
        try:
            ReplayPlanner.plan(group, replay_from)
        except ReplayUnsupportedError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "replay_unsupported",
                    "reason": str(exc),
                    "allowed": ReplayPlanner.allowed(group),
                },
            )


__all__ = ["ReplayGuard"]
