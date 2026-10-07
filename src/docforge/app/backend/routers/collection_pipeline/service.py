# ====== Code Summary ======
# CollectionStageApplier — the orchestration behind POST /collections/{id}/pipeline/stages/apply. It
# reads the collection's STORED pipeline (healed to the current engine), compiles one stage action on
# it, resolves secrets exactly like a PATCH (restore_blob_secrets: masked / omitted = keep the same
# provider's key), validates the result and — only when it is valid AND changed — persists it through
# the SAME canonicalize + config-version write a pipeline PATCH / snippet import uses. The returned
# stage view is built from the redacted blob, so no secret ever leaves the server. The read-modify-write
# is a compare-and-swap on the config version: a concurrent PATCH / merge between the read and the write
# makes the write conflict (never silently overwritten) — retried once on the fresh head, then a 409.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import HTTPException
from loggerplusplus import loggerplusplus
from pydantic import ValidationError

# ====== Internal Project Imports ======
from shared_libs.pipelines.blob_secrets import redact_blob_secrets, restore_blob_secrets
from shared_libs.pipelines.build import BuildError, GroupNodeBlob, ValidationMessage
from shared_libs.pipelines.ingest import BlobNormalizationError, BlobNormalizer
from shared_libs.pipelines.ingest.stages import StageAction, StageViewer, StateReader
from shared_libs.pipelines.validation import ValidationIssue
from shared_libs.services.db.facades import ConfigVersionConflictError
from shared_libs.services.db.postgresql.tables import Collection

# ====== Local Project Imports ======
from ...context import CONTEXT
from ..collections.blob_helpers import CollectionBlobHelpers
from .models import CollectionStageApplyRequest, CollectionStageApplyResponse

# A conflict means another write landed between our read and our write: recompute on the new head this
# many times before giving the caller a 409 (one retry absorbs an ordinary race without livelocking).
_CAS_ATTEMPTS = 2


class CollectionStageApplier:
    """Static apply → validate → persist sequence of a collection-scoped stage action."""

    logger = loggerplusplus.bind(identifier="CollectionStageApplier")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("CollectionStageApplier is a static-only class and cannot be instantiated.")

    @staticmethod
    def __stored_blob(collection: Collection) -> dict:
        """The collection's stored pipeline healed to the current engine (stamp stripped) — 422 if not."""
        try:
            return BlobNormalizer.normalize(collection.pipeline or {})
        except BlobNormalizationError as exc:
            raise HTTPException(
                status_code=422, detail=f"Stored pipeline cannot be migrated: {exc}"
            )

    @staticmethod
    def __verdict(candidate: dict) -> tuple[list[ValidationIssue], str | None]:
        """Build + validate a candidate blob; an unbuildable one is data (build_error), not a raise."""
        # The candidate holds RESTORED secrets: a malformed blob is reported through the input-free
        # ValidationMessage, never a raw ValidationError (whose text and traceback echo the input).
        try:
            group = CONTEXT.pipeline_builder.build(GroupNodeBlob.model_validate(candidate))
        except BuildError as exc:
            return [], str(exc)
        except ValidationError as exc:
            return [], f"invalid pipeline blob: {ValidationMessage.format(exc)}"
        return CONTEXT.graph_validator.validate(group), None

    @staticmethod
    def __redacted_stages(blob: dict) -> list:
        """The stage view of a blob with every provider secret masked."""
        public = GroupNodeBlob.model_validate(redact_blob_secrets(blob))
        return StageViewer.catalog(StateReader.read(public)).stages

    @staticmethod
    def __summary(action: StageAction) -> str:
        """The default config-version note naming the action and its stage."""
        return f"stage action: {action.action} '{action.stage}'"

    @classmethod
    async def _attempt(
        cls, collection: Collection, version: int, request: CollectionStageApplyRequest
    ) -> CollectionStageApplyResponse:
        """One compile → validate → CAS-persist pass on the head read at ``version``."""
        # 1. Compile the action on the stored pipeline (real secrets present — merge keeps them).
        base = GroupNodeBlob.model_validate(cls.__stored_blob(collection)).model_dump(mode="json")
        compiled, notices = CONTEXT.stage_compiler.apply(
            GroupNodeBlob.model_validate(base), request.action
        )

        # 2. Resolve secrets like a PATCH: masked / omitted = keep the same provider's stored key.
        candidate = restore_blob_secrets(compiled.model_dump(mode="json"), base) or {}
        issues, build_error = cls.__verdict(candidate)
        response = CollectionStageApplyResponse(
            collection_id=str(collection.id),
            persisted=False,
            needs_reindex=bool(collection.needs_reindex),
            stages=cls.__redacted_stages(candidate),
            valid=not issues and build_error is None,
            issues=issues,
            notices=list(notices),
            build_error=build_error,
        )

        # 3. Never store a broken pipeline, never mint a version for a no-op.
        if not response.valid:
            response.notices.append("not persisted — the resulting pipeline is invalid")
            return response
        if candidate == base:
            response.notices.append("not persisted — the action changed nothing")
            return response

        # 4. Persist through the PATCH's canonicalize + config-version write, conditional on the head
        #    version this pass read (raises ConfigVersionConflictError if another write landed).
        response.needs_reindex = await CONTEXT.database.collections.update_config(
            collection.id,
            pipeline=CollectionBlobHelpers.canonical_pipeline(candidate),
            note=request.note or cls.__summary(request.action),
            expected_version=version,
        )
        response.persisted = True
        return response

    @classmethod
    async def apply(
        cls, collection_id: uuid.UUID, request: CollectionStageApplyRequest
    ) -> CollectionStageApplyResponse:
        """
        Apply one stage action to a collection's stored pipeline and persist a valid change.

        Args:
            collection_id (uuid.UUID): The target collection (its stored pipeline is the base).
            request (CollectionStageApplyRequest): The action (+ optional snapshot note).

        Returns:
            CollectionStageApplyResponse: The redacted stage view, validity, notices and whether
            the change was persisted.

        Raises:
            HTTPException: 404 when the collection vanished; 422 when the stored pipeline cannot be
                healed to the current engine; 409 when concurrent config writes kept winning the race.
        """
        # 1. Read the head (version, then row) and run one pass; a lost CAS re-reads and recomputes.
        for _ in range(_CAS_ATTEMPTS):
            collection, version = await CONTEXT.database.collections.config_head(collection_id)
            if collection is None:
                raise HTTPException(
                    status_code=404, detail=f"Collection {collection_id} not found."
                )
            try:
                response = await cls._attempt(collection, version, request)
            except ConfigVersionConflictError as exc:
                cls.logger.warning(f"Stage apply lost a concurrent config race, recomputing: {exc}")
                continue
            if response.persisted:
                cls.logger.info(
                    f"Collection {collection_id}: persisted stage action '{request.action.action}'"
                )
            return response

        # 2. Every pass lost the race — surface it instead of overwriting someone else's change.
        raise HTTPException(
            status_code=409,
            detail=(
                f"Collection {collection_id}: its pipeline was changed concurrently while this stage "
                f"action was applied — re-read the pipeline and retry."
            ),
        )


__all__ = ["CollectionStageApplier"]
