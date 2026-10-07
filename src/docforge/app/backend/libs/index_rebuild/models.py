# ====== Code Summary ======
# The rebuild_index API response contract.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field


class RebuildIndexAccepted(BaseModel):
    """
    A queued index rebuild — poll the job.

    Attributes:
        collection_id (str): The collection being rebuilt.
        job_id (str): The tracked ``rebuild_index`` job (GET /jobs/{job_id}).
    """

    collection_id: str = Field(description="The collection whose index is being rebuilt.")
    job_id: str = Field(description="The tracked rebuild_index job — poll GET /jobs/{job_id}.")


__all__ = ["RebuildIndexAccepted"]
