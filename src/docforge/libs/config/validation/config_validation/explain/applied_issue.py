# ====== Code Summary ======
# AppliedIssue — a single non-blocking validation warning surfaced to the caller
# inside the ConfigApplied transparency envelope.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from pydantic import BaseModel


class AppliedIssue(BaseModel):
    """A single non-blocking validation warning surfaced to the caller."""

    code: str
    field: str
    message: str
