# ====== Code Summary ======
# The read_text projection of a collection contract. The collection read routes are reachable with
# READ_TEXT (a business agent needs the lean contract — identity, limits, metadata schema, title
# field) but the ingestion/search pipeline blobs are internals reserved to READ_TECHNICAL. Rather than
# refusing the whole route, a caller without READ_TECHNICAL gets the contract with both blobs nulled.

# ====== Standard Library Imports ======
from typing import TypeVar

# ====== Local Project Imports ======
from ...libs.auth import AuthPrincipal, AuthzGuard, Capability
from .models import CollectionModel

_Model = TypeVar("_Model", bound=CollectionModel)


class CollectionTechnicalView:
    """Static helper withholding a collection's pipeline/search blobs from non-technical readers."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "CollectionTechnicalView is a static-only class and cannot be instantiated."
        )

    @staticmethod
    def shape(models: list[_Model], principal: AuthPrincipal) -> list[_Model]:
        """
        Null the pipeline/search blobs of every model unless the caller holds READ_TECHNICAL.

        Args:
            models (list[CollectionModel]): The fully-built contracts (blobs already secret-masked).
            principal (AuthPrincipal): The authenticated caller.

        Returns:
            list[CollectionModel]: The same models when the caller is technical, else copies with
            ``pipeline`` and ``search`` set to null.
        """
        # 1. A technical (or full-access) reader sees the blobs untouched.
        if AuthzGuard.holds(principal, Capability.READ_TECHNICAL):
            return models

        # 2. Everyone else gets the lean contract — the blobs are withheld, never refused.
        return [model.model_copy(update={"pipeline": None, "search": None}) for model in models]


__all__ = ["CollectionTechnicalView"]
