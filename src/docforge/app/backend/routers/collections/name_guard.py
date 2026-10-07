# ====== Code Summary ======
# CollectionNameGuard — the 409 pre-check a collection create/rename runs on its name: it must be free
# among collection names AND must not equal a collection alias (case-insensitively), so an alias and a
# collection never share a name. The cross-table check is a best-effort pre-check (no cross-table
# constraint exists); a lost race only costs that UX guarantee — ref resolution never reads collection
# names (a ref is a UUID or an alias), so it can never become ambiguous.

# ====== Third-Party Library Imports ======
from fastapi import HTTPException

# ====== Local Project Imports ======
from ...context import CONTEXT


class CollectionNameGuard:
    """Static name pre-check shared by collection create and rename."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("CollectionNameGuard is a static-only class and cannot be instantiated.")

    @staticmethod
    async def assert_free(name: str) -> None:
        """
        Refuse a collection name already taken by a collection or a collection alias.

        Args:
            name (str): The requested collection name.

        Raises:
            HTTPException: 409 naming which namespace already holds it.
        """
        # 1. Collection names are unique (the UNIQUE constraint is the race backstop).
        if await CONTEXT.database.collections.get_by_name(name) is not None:
            raise HTTPException(status_code=409, detail=f"Collection '{name}' already exists.")
        # 2. A collection may not be named like an alias (both ways — the alias PUT checks the other).
        if await CONTEXT.database.collection_aliases.name_is_alias(name):
            raise HTTPException(
                status_code=409,
                detail=f"'{name}' is already a collection alias; aliases and collection names must "
                f"stay distinct.",
            )


__all__ = ["CollectionNameGuard"]
