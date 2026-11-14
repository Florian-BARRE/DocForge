# ====== Code Summary ======
# ConstraintViolation — the one decoder of "which constraint did this IntegrityError violate?". asyncpg
# carries the violated constraint (or unique-index) name as ``constraint_name`` on its native error;
# under SQLAlchemy's asyncpg adapter that native error is the wrapper's ``__cause__`` (the adapter's own
# ``error.orig`` may carry none), so both hops are inspected. Matching the exact name is what tells a
# lost race (a benign conflict) apart from any other integrity failure, which must still surface.

# ====== Third-Party Library Imports ======
from sqlalchemy.exc import IntegrityError


class ConstraintViolation:
    """Static recogniser of a named constraint violation inside a driver IntegrityError."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ConstraintViolation is a static-only class and cannot be instantiated.")

    @staticmethod
    def matches(error: IntegrityError, constraint_name: str) -> bool:
        """
        Decide whether an IntegrityError violated exactly the named constraint (or unique index).

        Args:
            error (IntegrityError): The error raised by the flush/commit of the guarded write.
            constraint_name (str): The constraint or partial-unique-index name to match.

        Returns:
            bool: True only when the driver error (or its ``__cause__``) reports that exact name.
        """
        # 1. Walk the driver error and its __cause__ (the asyncpg native error carrying constraint_name).
        orig = getattr(error, "orig", None)
        candidates = (orig, getattr(orig, "__cause__", None))
        return any(
            getattr(candidate, "constraint_name", None) == constraint_name
            for candidate in candidates
        )


__all__ = ["ConstraintViolation"]
