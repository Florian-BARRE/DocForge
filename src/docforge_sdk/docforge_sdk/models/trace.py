# ====== Code Summary ======
# Leaf model for the explicit trace-payload purge — mirrors the backend TracePurgeResult. Kept in its
# own module (importing only pydantic) so both the collections and documents resources can reference
# it without any cross-module import.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class TracePurgeResult(BaseModel):
    """
    The outcome of an explicit trace-payload purge (a collection's or a single document's).

    Idempotent by contract: a purge over a scope that stored no full-trace payloads returns zeros
    rather than an error. Both counters are best-effort tallies (a storage error during the purge is
    swallowed server-side), so the call always succeeds.

    Attributes:
        purged_jobs (int): Jobs in scope whose trace references were cleared (0 when the scope has
            no jobs).
        deleted_objects (int): Object-store objects removed across those jobs (0 when nothing was
            stored).
    """

    purged_jobs: int = Field(
        description="Jobs in scope whose trace references were cleared (0 when the scope has no jobs)."
    )
    deleted_objects: int = Field(
        description="Object-store objects removed across those jobs (0 when nothing was stored)."
    )


__all__ = ["TracePurgeResult"]
