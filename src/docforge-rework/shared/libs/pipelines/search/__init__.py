# ---------------------- The search pipeline ---------------------- #
# Its facade (families, palette, default topology) and the read-only capability port a retrieve/
# hydrate node reaches through the engine's bind() seam. Importing the facade registers every
# search node family.
from .pipeline import SearchPipeline
from .ports import COLLECTION_READ_CAPABILITY, CollectionReadPort, read_port

# ------------------- Public API ------------------- #
__all__ = ["SearchPipeline", "CollectionReadPort", "COLLECTION_READ_CAPABILITY", "read_port"]
