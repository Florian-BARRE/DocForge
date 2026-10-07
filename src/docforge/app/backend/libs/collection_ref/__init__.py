# ---------------------- Alias name grammar ---------------------- #
from .alias_name import ALIAS_SCOPE_PREFIX, CollectionAliasName

# ---------------------- Ref resolution (UUID or alias) ---------------------- #
from .resolver import (
    RESOLVED_STATE_KEY,
    CollectionRef,
    CollectionRefQuery,
    CollectionRefResolver,
    OptionalCollectionRefQuery,
)

# ------------------- Public API ------------------- #
__all__ = [
    "ALIAS_SCOPE_PREFIX",
    "CollectionAliasName",
    "RESOLVED_STATE_KEY",
    "CollectionRef",
    "CollectionRefQuery",
    "CollectionRefResolver",
    "OptionalCollectionRefQuery",
]
