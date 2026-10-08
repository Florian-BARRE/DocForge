# ====== Code Summary ======
# The collection-name UNIQUE race: DuplicateCollectionNameError (the domain error a create/rename that
# lost the race raises — the router maps it to a 409) and CollectionNameConflict, which recognises that
# exact constraint violation inside a driver IntegrityError (any other integrity failure stays a bug).

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus
from sqlalchemy.exc import IntegrityError

# The collection-name UNIQUE constraint two concurrent creates race on. Name is stable via the schema
# naming convention (uq_<table>_<column>) → the ``unique=True`` on ``collection.name``. asyncpg carries
# the violated constraint name on its native error, nested as the SQLAlchemy wrapper's ``__cause__``.
_NAME_UNIQUE_CONSTRAINT = "uq_collection_name"


class DuplicateCollectionNameError(Exception):
    """Raised when a create loses the collection-name UNIQUE race — the router maps it to a 409."""

    def __init__(self, name: str) -> None:
        """
        Args:
            name (str): The already-taken collection name.
        """
        super().__init__(f"Collection '{name}' already exists.")
        self.name = name


class CollectionNameConflict:
    """Static recogniser of the collection-name UNIQUE violation inside a driver error."""

    logger = loggerplusplus.bind(identifier="CollectionNameConflict")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("CollectionNameConflict is a static-only class and cannot be instantiated.")

    @staticmethod
    def is_duplicate_name(error: IntegrityError) -> bool:
        """
        Decide whether an IntegrityError is the collection-name UNIQUE violation (a lost create race).

        Args:
            error (IntegrityError): The error raised by the contract INSERT's flush.

        Returns:
            bool: True only when the violated constraint is ``uq_collection_name``.
        """
        # 1. Walk the driver error and its __cause__ (the asyncpg native error carrying constraint_name)
        #    and match the name guard — so an unrelated integrity failure still surfaces as a real error.
        orig = getattr(error, "orig", None)
        candidates = (orig, getattr(orig, "__cause__", None))
        return any(
            getattr(candidate, "constraint_name", None) == _NAME_UNIQUE_CONSTRAINT
            for candidate in candidates
        )


__all__ = ["CollectionNameConflict", "DuplicateCollectionNameError"]
