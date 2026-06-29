# ====== Code Summary ======
# The chunk-scope step's own failure type — raised on an unexpected error while generating chunk-scope
# metadata. Each individual provider call self-degrades to {} on failure, so this error is reserved
# for genuine faults (e.g. a cache backend outage) rather than a degraded LLM response.

# ====== Internal Project Imports ======
from ..base import IngestStageMetagenStepError


class IngestStageMetagenStepChunkScopeError(IngestStageMetagenStepError):
    """Raised when the chunk-scope generation step fails unexpectedly."""

    code = "metagen_chunk_scope_failed"
    description = "The metagen chunk-scope step failed to generate per-chunk metadata."


__all__ = ["IngestStageMetagenStepChunkScopeError"]
