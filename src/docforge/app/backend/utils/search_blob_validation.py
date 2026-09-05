# ====== Code Summary ======
# Write-time validation of a stored SEARCH graph blob. It layers a terminal-CONTRACT check on top of
# the shared structural PipelineBlobValidator: a search blob must not only build + pass the graph
# validator, it must ALSO be a genuine search pipeline — one that ends on a node producing a
# SearchResult (the deliver/hits contract the inline runner asserts at run time). This closes the gap
# where a structurally-valid-but-non-search graph (an ingest topology, or a search graph missing its
# deliver terminal) stored a 200, then made every subsequent query raise SearchRunError → HTTP 500.
# The terminal contract itself lives in shared_libs (SearchResultContract), shared verbatim with the
# worker's import-time validator; this class only maps a failure to the write boundary's HTTP 422.

# ====== Third-Party Library Imports ======
from fastapi import HTTPException
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.search import SearchPipeline
from shared_libs.pipelines.validation import SearchResultContract

# ====== Local Project Imports ======
from .pipeline_validation import PipelineBlobValidator


class SearchBlobValidator:
    """
    Static validator for a stored search graph blob (structural + terminal contract → 422).

    Composes the shared structural core of ``PipelineBlobValidator`` (build + graph validation) with
    the SEARCH palette scope (only kinds the search pipeline is built from) and the shared
    ``SearchResultContract`` terminal check that mirrors the inline runner's runtime assert: the
    built graph must terminate on a node whose ``Produces`` face yields a ``SearchResult``. A
    structurally valid but non-search graph (an ingest topology, an ingest kind smuggled in, or a
    search graph with its ``deliver/hits`` terminal removed) is therefore rejected at the WRITE
    boundary — never stored to 500 on every query.
    """

    logger = loggerplusplus.bind(identifier="SearchBlobValidator")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SearchBlobValidator is a static-only class and cannot be instantiated.")

    @classmethod
    def validate(cls, blob: dict) -> None:
        """
        Structurally validate a search blob AND assert it is a genuine search pipeline.

        Args:
            blob (dict): The stored search graph configuration to check.

        Raises:
            HTTPException: 422 when the blob cannot be built or fails structural validation
                (delegated to ``PipelineBlobValidator``), contains a kind foreign to the search
                palette, or does not terminate on a ``deliver/hits`` node producing a SearchResult.
        """
        # 1. Structural validation first — build + graph validator (shared core, raises 422). The
        #    pipeline-agnostic core is used (NOT PipelineBlobValidator.validate, which would apply
        #    the INGEST scope) so the search-specific scope can be enforced next on the same graph.
        group = PipelineBlobValidator.build_and_check_structure(blob)

        # 2. Reject any kind that does not belong to the SEARCH pipeline's palette.
        PipelineBlobValidator.enforce_palette(group, SearchPipeline.allowed_kinds())

        # 3. Assert the TERMINAL contract (the runner's runtime assert, checked at build time so a
        #    non-search graph fails at the write edge).
        if not SearchResultContract.terminates_on_search_result(group):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Stored search blob is not a valid search pipeline — it must end on a "
                    "deliver/hits node producing a SearchResult."
                ),
            )


__all__ = ["SearchBlobValidator"]
