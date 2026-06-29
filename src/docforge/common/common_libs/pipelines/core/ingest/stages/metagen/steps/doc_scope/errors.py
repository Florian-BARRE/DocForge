# ====== Code Summary ======
# The document-scope step's own failure type — raised on an unexpected error while generating the
# document-scope metadata. The single provider call self-degrades to {} on failure, so this error is
# reserved for genuine faults rather than a degraded LLM response.

# ====== Internal Project Imports ======
from ..base import IngestStageMetagenStepError


class IngestStageMetagenStepDocScopeError(IngestStageMetagenStepError):
    """Raised when the document-scope generation step fails unexpectedly."""

    code = "metagen_doc_scope_failed"
    description = "The metagen document-scope step failed to generate document-level metadata."


__all__ = ["IngestStageMetagenStepDocScopeError"]
