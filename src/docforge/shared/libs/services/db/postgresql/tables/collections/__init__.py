# ---------------------- Collection domain ---------------------- #
from .collection import Collection
from .collection_alias import COLLECTION_ALIAS_PATTERN, CollectionAlias
from .metadata_field import MetadataField

# ------------------- Public API ------------------- #
__all__ = ["COLLECTION_ALIAS_PATTERN", "Collection", "CollectionAlias", "MetadataField"]
