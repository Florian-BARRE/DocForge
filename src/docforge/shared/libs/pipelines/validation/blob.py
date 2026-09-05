# ====== Code Summary ======
# BlobStructureValidator — the store-agnostic, HTTP-free structural validation of a stored pipeline
# blob (ingest OR search). It builds the blob into a live graph and runs the graph validator, and for
# a search blob additionally asserts the SearchResult terminal contract. Any problem is raised as a
# BlobValidationError carrying the human message + the collected issues. The app's write-boundary
# validators raise HTTP 422 from the SAME building blocks; this class is the worker-side equivalent
# used by the collection-import restore, which cannot import the app's FastAPI-coupled validators —
# so a malformed or hostile bundle's graph blobs are rejected BEFORE the new collection is persisted,
# exactly like every other write path, instead of being stored verbatim to brick the collection.

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.build import BuildError, PipelineBuilder

# ====== Local Project Imports ======
from .issues import ValidationIssue
from .search_contract import SearchResultContract
from .validator import GraphValidator


class BlobValidationError(Exception):
    """
    Raised when a stored pipeline/search blob fails structural (or terminal-contract) validation.

    Carries the human-readable reason and, when the failure is structural, the full list of
    collected issues so a caller can surface every problem at once.
    """

    def __init__(self, message: str, issues: list[ValidationIssue] | None = None) -> None:
        """
        Args:
            message (str): The human-readable failure reason.
            issues (list[ValidationIssue] | None): Every structural issue found (None for a
                build/terminal failure that is not a graph-validator issue list).
        """
        super().__init__(message)
        self.issues = issues or []


class BlobStructureValidator(LoggerClass):
    """
    Store-agnostic structural validator for a pipeline blob (build + graph validation + terminal).

    Stateless across calls: it holds a ``PipelineBuilder`` and a ``GraphValidator`` (both stateless,
    reading the process-global NodeRegistry). ``validate_ingest`` checks build + structure; a valid
    search blob must additionally terminate on a SearchResult-producing node (``validate_search``).
    """

    def __init__(
        self,
        builder: PipelineBuilder | None = None,
        validator: GraphValidator | None = None,
    ) -> None:
        """
        Args:
            builder (PipelineBuilder | None): The blob→graph builder (a fresh one when omitted).
            validator (GraphValidator | None): The structural validator (a fresh one when omitted).
        """
        LoggerClass.__init__(self)
        self._builder = builder or PipelineBuilder()
        self._validator = validator or GraphValidator()

    def __build_and_validate(self, blob: dict):
        """
        Build the blob and run the structural validator, returning the built graph.

        Args:
            blob (dict): The stored pipeline configuration to check.

        Returns:
            Group: The built, structurally-valid graph (ready for a further terminal check).

        Raises:
            BlobValidationError: When the blob cannot be built or has structural issues.
        """
        # 1. Build the graph — an unknown/removed node kind or malformed blob raises BuildError.
        try:
            group = self._builder.build(blob)
        except BuildError as exc:
            raise BlobValidationError(f"cannot be built: {exc}") from exc

        # 2. Structural validation — collect every issue into one error.
        issues = self._validator.validate(group)
        if issues:
            summary = "; ".join(f"{issue.location}: {issue.message}" for issue in issues)
            raise BlobValidationError(f"failed structural validation ({summary})", issues)
        return group

    def validate_ingest(self, blob: dict) -> None:
        """
        Structurally validate an INGEST pipeline blob (build + graph validation).

        Args:
            blob (dict): The stored ingest pipeline configuration.

        Raises:
            BlobValidationError: When the blob cannot be built or fails structural validation.
        """
        # 1. Build + structural validation is the whole ingest contract.
        self.__build_and_validate(blob)

    def validate_search(self, blob: dict) -> None:
        """
        Structurally validate a SEARCH blob AND assert it is a genuine search pipeline.

        Args:
            blob (dict): The stored search graph configuration.

        Raises:
            BlobValidationError: When the blob cannot be built, fails structural validation, or does
                not terminate on a ``deliver/hits`` node producing a SearchResult.
        """
        # 1. Structural validation first (build + graph validator).
        group = self.__build_and_validate(blob)

        # 2. Terminal contract — a non-search graph is rejected here, mirroring the runner's assert.
        if not SearchResultContract.terminates_on_search_result(group):
            raise BlobValidationError(
                "is not a valid search pipeline — it must end on a deliver/hits node producing "
                "a SearchResult"
            )


__all__ = ["BlobStructureValidator", "BlobValidationError"]
