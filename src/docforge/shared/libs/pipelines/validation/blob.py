# ====== Code Summary ======
# BlobStructureValidator — the store-agnostic, HTTP-free structural validation of a stored pipeline
# blob (ingest OR search). It builds the blob into a live graph and runs the graph validator, and for
# a search blob additionally asserts the SearchResult terminal contract. Any problem is raised as a
# BlobValidationError carrying the human message + the collected issues. The app's write-boundary
# validators raise HTTP 422 from the SAME building blocks; this class is the worker-side equivalent
# used by the collection-import restore, which cannot import the app's FastAPI-coupled validators —
# so a malformed or hostile bundle's graph blobs are rejected BEFORE the new collection is persisted,
# exactly like every other write path, instead of being stored verbatim to brick the collection.

# ====== Standard Library Imports ======
from typing import Protocol

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from shared_libs.pipelines.build import BuildError, PipelineBuilder

# ====== Local Project Imports ======
from .issues import ValidationIssue
from .palette import PaletteScopeValidator
from .search_contract import SearchResultContract
from .validator import GraphValidator


class PipelinePalettes(Protocol):
    """
    The palette scopes of the pipeline kinds, injected into the validator.

    ``PipelineRegistry`` satisfies it (the class itself, its ``allowed_kinds`` is a classmethod).
    Declaring the port here keeps this package free of any import of the ingest/search facades,
    which themselves import this package (the former validation <-> ingest/search cycle).
    """

    def allowed_kinds(self, pipeline_key: str) -> dict[str, set[str]]:
        """Return the (family → allowed kinds) map of the pipeline kind ``pipeline_key``."""
        ...


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

    Stateless across calls: it holds a ``PipelineBuilder``, a ``GraphValidator`` (both stateless,
    reading the process-global NodeRegistry) and the injected pipeline palettes. ``validate_ingest``
    checks build + structure; a valid search blob must additionally terminate on a
    SearchResult-producing node (``validate_search``).
    """

    def __init__(
        self,
        builder: PipelineBuilder | None = None,
        validator: GraphValidator | None = None,
        palettes: PipelinePalettes | None = None,
    ) -> None:
        """
        Args:
            builder (PipelineBuilder | None): The blob→graph builder (a fresh one when omitted).
            validator (GraphValidator | None): The structural validator (a fresh one when omitted).
            palettes (PipelinePalettes | None): Where the per-pipeline palette scope comes from
                (the ``PipelineRegistry`` when omitted, resolved on first use).
        """
        LoggerClass.__init__(self)
        self._builder = builder or PipelineBuilder()
        self._validator = validator or GraphValidator()
        self._palettes = palettes

    def __palettes(self) -> PipelinePalettes:
        """
        Return the injected palettes, defaulting to the PipelineRegistry on first use.

        The default is the ONE place this package reaches the composition root. It stays a lazy
        import because the registry imports the ingest/search facades, which import this package;
        resolving it also registers every node family before the blob is built. A caller that
        injects ``palettes`` never triggers it.

        Returns:
            PipelinePalettes: The palette source used by ``validate_ingest`` / ``validate_search``.
        """
        if self._palettes is None:
            from shared_libs.pipelines.pipeline_registry import PipelineRegistry

            self._palettes = PipelineRegistry
        return self._palettes

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

    def __enforce_palette(self, group, allowed_kinds: dict[str, set[str]]) -> None:
        """
        Reject any node whose (family, kind) is outside a pipeline's palette.

        Args:
            group: The built, structurally-valid graph to scope-check.
            allowed_kinds (dict[str, set[str]]): The target pipeline's family → allowed kinds map.

        Raises:
            BlobValidationError: When any node is foreign to the pipeline's palette.
        """
        # 1. A structurally valid graph can still be wired from a FOREIGN kind — reject it here.
        issues = PaletteScopeValidator.validate(group, allowed_kinds)
        if issues:
            summary = "; ".join(f"{issue.location}: {issue.message}" for issue in issues)
            raise BlobValidationError(f"uses kinds outside the palette ({summary})", issues)

    def validate_ingest(self, blob: dict) -> None:
        """
        Structurally validate an INGEST pipeline blob (build + graph validation + palette scope).

        Args:
            blob (dict): The stored ingest pipeline configuration.

        Raises:
            BlobValidationError: When the blob cannot be built, fails structural validation, or
                contains a kind foreign to the ingestion pipeline's palette.
        """
        # 1. Resolve the ingestion palette first (this also registers the node families the build
        #    needs), then build + validate, then reject any kind foreign to that palette.
        allowed_kinds = self.__palettes().allowed_kinds("ingest")
        group = self.__build_and_validate(blob)
        self.__enforce_palette(group, allowed_kinds)

    def validate_search(self, blob: dict) -> None:
        """
        Structurally validate a SEARCH blob AND assert it is a genuine search pipeline.

        Args:
            blob (dict): The stored search graph configuration.

        Raises:
            BlobValidationError: When the blob cannot be built, fails structural validation,
                contains a kind foreign to the search palette, or does not terminate on a
                ``deliver/hits`` node producing a SearchResult.
        """
        # 1. Resolve the search palette first (see validate_ingest), then structural validation
        #    (build + graph validator).
        allowed_kinds = self.__palettes().allowed_kinds("search")
        group = self.__build_and_validate(blob)

        # 2. Reject any kind that does not belong to the SEARCH pipeline's palette.
        self.__enforce_palette(group, allowed_kinds)

        # 3. Terminal contract — a non-search graph is rejected here, mirroring the runner's assert.
        if not SearchResultContract.terminates_on_search_result(group):
            raise BlobValidationError(
                "is not a valid search pipeline — it must end on a deliver/hits node producing "
                "a SearchResult"
            )


__all__ = ["BlobStructureValidator", "BlobValidationError", "PipelinePalettes"]
