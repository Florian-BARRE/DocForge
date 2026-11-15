# ====== Code Summary ======
# Typed JSON error bodies of the model-host micro-services. The envelope `{"detail": {"error": ...}}`
# is the one the servers already return for their 413/422/503 answers, so a typed 500 is read by the
# same clients; the 500 additionally carries a `correlation_id` that matches the server log line.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    """The inner object of an error response.

    Attributes:
        error (str): Stable, non-leaky message (never `str(exception)`).
        correlation_id (str): Id to quote to find the full exception in the server logs.
    """

    error: str = Field(..., description="Stable error message; never an internal detail.")
    correlation_id: str = Field(..., description="Id of the matching server log entry.")


class ErrorResponse(BaseModel):
    """Body of a typed 500 response.

    Attributes:
        detail (ErrorDetail): The error and its correlation id.
    """

    detail: ErrorDetail
