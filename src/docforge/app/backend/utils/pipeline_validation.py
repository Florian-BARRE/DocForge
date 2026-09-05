# ====== Code Summary ======
# Shared structural validation of a stored pipeline blob: build it, then run the graph validator,
# turning any build error or validation issue into a precise HTTP 422. Used by the collections
# router (on write) AND the documents router (on upload, before any spend), so a stale collection
# blob — one that names a node kind the registry no longer knows — is rejected with a clear error
# instead of failing silently in the worker after bytes are stored and a job is enqueued.
#
# On top of the pipeline-agnostic structural check, ``validate`` enforces the INGEST palette scope:
# a blob may only contain kinds the ingestion pipeline is built from (its FAMILIES + FAMILY_KINDS
# allowlist, internal wiring included). A search-only kind smuggled into an ingest graph — which
# builds and passes structural validation but is wired wrong — is therefore rejected at the write
# boundary. The structural core is exposed separately so the search write validator can reuse it
# without inheriting the ingest scope.

# ====== Third-Party Library Imports ======
from fastapi import HTTPException
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import Group
from shared_libs.pipelines.build import BuildError
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.validation import PaletteScopeValidator

# ====== Local Project Imports ======
from ..context import CONTEXT


class PipelineBlobValidator:
    """
    Static structural validator for a pipeline blob (build + graph validation → 422).

    A blob is DATA. When it cannot be built (e.g. it names a node kind no longer in the
    registry) or fails structural validation, that is a client-visible 422 carrying the
    offending node/kind and every issue — never a 500 and never a silently enqueued job.
    Both the collections router (validate on write) and the documents router (validate on
    upload, before any spend) share this single chokepoint. ``validate`` additionally enforces
    the ingestion palette scope; the ``build_and_check_structure`` / ``enforce_palette`` building
    blocks are reused by the search write validator under the SEARCH scope.
    """

    logger = loggerplusplus.bind(identifier="PipelineBlobValidator")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("PipelineBlobValidator is a static-only class and cannot be instantiated.")

    @classmethod
    def build_and_check_structure(cls, blob: dict) -> Group:
        """
        Build a pipeline blob and run the pipeline-agnostic structural validator (→ 422).

        Args:
            blob (dict): The stored pipeline configuration to check.

        Returns:
            Group: The built, structurally-valid graph (for a further palette/terminal check).

        Raises:
            HTTPException: 422 when the blob cannot be built (message names the offending
                node/kind) or when the built graph has structural validation issues.
        """
        # 1. Build the graph — an unknown/removed node kind raises BuildError here.
        try:
            group = CONTEXT.pipeline_builder.build(blob)
        except BuildError as exc:
            raise HTTPException(status_code=422, detail=f"Pipeline blob cannot be built: {exc}")

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
        return group

    @classmethod
    def enforce_palette(cls, group: Group, allowed_kinds: dict[str, set[str]]) -> None:
        """
        Reject any node whose (family, kind) is outside a pipeline's palette (→ 422).

        Args:
            group (Group): The built graph to scope-check.
            allowed_kinds (dict[str, set[str]]): The target pipeline's family → allowed kinds map
                (``IngestPipeline.allowed_kinds()`` / ``SearchPipeline.allowed_kinds()``).

        Raises:
            HTTPException: 422 listing every ``kind_not_in_palette`` issue found.
        """
        # 1. A structurally valid graph can still be wired from a FOREIGN kind — reject it here.
        issues = PaletteScopeValidator.validate(group, allowed_kinds)
        if issues:
            raise HTTPException(
                status_code=422,
                detail=[
                    {"code": issue.code.value, "location": issue.location, "message": issue.message}
                    for issue in issues
                ],
            )

    @classmethod
    def validate(cls, blob: dict) -> None:
        """
        Build, structurally validate, and INGEST-palette-scope a pipeline blob (→ 422).

        Args:
            blob (dict): The stored pipeline configuration to check.

        Raises:
            HTTPException: 422 when the blob cannot be built, fails structural validation, or
                contains a kind that does not belong to the ingestion pipeline's palette.
        """
        # 1. Build + structure first, then reject any kind foreign to the ingestion palette.
        group = cls.build_and_check_structure(blob)
        cls.enforce_palette(group, IngestPipeline.allowed_kinds())


__all__ = ["PipelineBlobValidator"]
