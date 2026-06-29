# ====== Code Summary ======
# The assemble-doc-meta step's own failure type — raised on an unexpected error while merging the
# document-level metadata. A pure merge that should not normally fail; the error exists to keep the
# feedback tree precise should an input be malformed.

# ====== Internal Project Imports ======
from ..base import IngestStageMetagenStepError


class IngestStageMetagenStepAssembleDocMetaError(IngestStageMetagenStepError):
    """Raised when the assemble-doc-meta step fails unexpectedly."""

    code = "metagen_assemble_doc_meta_failed"
    description = "The metagen assemble-doc-meta step failed to merge the document-level metadata."


__all__ = ["IngestStageMetagenStepAssembleDocMetaError"]
