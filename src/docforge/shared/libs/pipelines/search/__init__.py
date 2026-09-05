# ---------------------- The search pipeline ---------------------- #
# Its facade (families, palette, default topology) and the read-only capability port a retrieve/
# hydrate node reaches through the engine's bind() seam. Importing the facade registers every
# search node family.
from .pipeline import SearchPipeline
from .ports import COLLECTION_READ_CAPABILITY, CollectionReadPort, read_port

# ---------------------- Read-side auto-heal ---------------------- #
# The search analog of the ingest BlobNormalizer: reconcile a stored search blob's node configs to
# the current registry at read time, so registry drift self-heals instead of bricking a run.
from .normalizer import SearchBlobNormalizationError, SearchBlobNormalizer

# ------------------- Public API ------------------- #
__all__ = [
    "SearchPipeline",
    "CollectionReadPort",
    "COLLECTION_READ_CAPABILITY",
    "read_port",
    "SearchBlobNormalizer",
    "SearchBlobNormalizationError",
]
