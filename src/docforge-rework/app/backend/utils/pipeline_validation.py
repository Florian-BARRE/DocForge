# ====== Code Summary ======
# Shared structural validation of a stored pipeline blob: build it, then run the graph validator,
# turning any build error or validation issue into a precise HTTP 422. Used by the collections
# router (on write) AND the documents router (on upload, before any spend), so a stale collection
# blob — one that names a node kind the registry no longer knows — is rejected with a clear error
# instead of failing silently in the worker after bytes are stored and a job is enqueued.

# ====== Third-Party Library Imports ======
from fastapi import HTTPException
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.build import BuildError

# ====== Local Project Imports ======
from ..context import CONTEXT


class PipelineBlobValidator:
    """
    Static structural validator for a pipeline blob (build + graph validation → 422).

    A blob is DATA. When it cannot be built (e.g. it names a node kind no longer in the
    registry) or fails structural validation, that is a client-visible 422 carrying the
    offending node/kind and every issue — never a 500 and never a silently enqueued job.
    Both the collections router (validate on write) and the documents router (validate on
    upload, before any spend) share this single chokepoint.
    """

    logger = loggerplusplus.bind(identifier="PipelineBlobValidator")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "PipelineBlobValidator is a static-only class and cannot be instantiated."
        )

    @classmethod
    def validate(cls, blob: dict) -> None:
        """
        Build and structurally validate a pipeline blob, raising 422 on any problem.

        Args:
            blob (dict): The stored pipeline configuration to check.

        Raises:
            HTTPException: 422 when the blob cannot be built (message names the offending
                node/kind) or when the built graph has structural validation issues (every
                issue is returned in the detail payload).
        """
        # 1. Build the graph — an unknown/removed node kind raises BuildError here.
        try:
            group = CONTEXT.pipeline_builder.build(blob)
        except BuildError as exc:
            raise HTTPException(
                status_code=422, detail=f"Pipeline blob cannot be built: {exc}"
            )

        # 2. Structural validation — collect every issue into one 422 payload.
        issues = CONTEXT.graph_validator.validate(group)
        if issues:
            raise HTTPException(
                status_code=422,
                detail=[
                    {"code": issue.code.value, "location": issue.location, "message": issue.message}
                    for issue in issues
                ],
            )


__all__ = ["PipelineBlobValidator"]
