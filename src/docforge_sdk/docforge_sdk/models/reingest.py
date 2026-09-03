# ====== Code Summary ======
# Leaf model shared by the collections and corpus modules — kept here (importing only pydantic) so
# both can reference it without a circular import (collections ⇄ estimate ⇄ corpus).

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class ReingestJobHandle(BaseModel):
    """
    One enqueued re-ingestion — poll the job for status/progress.

    Attributes:
        document_id (str): The document being re-ingested.
        job_id (str): The fresh ingestion job driving its lifecycle.
    """

    document_id: str = Field(description="The document being re-ingested.")
    job_id: str = Field(description="The fresh ingestion job driving its lifecycle.")


__all__ = ["ReingestJobHandle"]
