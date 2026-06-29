# ====== Code Summary ======
# IO contract for the content-address step: it reads the original bytes / filename / doc id from its
# parent stage input (FromParent) and produces the content address (sha256), the effective doc id,
# the resolved original format, and the object-store key the original was uploaded under.

# ====== Third-Party Library Imports ======
from typing import Annotated

# ====== Internal Project Imports ======
from common_libs.pipelines import FromParent, NodeInput, NodeOutput


class IngestStageIngestStepContentAddressInput(NodeInput):
    """
    Input of the content-address step (all read from the parent stage input).

    Attributes:
        original_bytes (bytes): The raw original file bytes.
        filename (str): The original filename (its extension resolves the format).
        doc_id (str | None): A pre-assigned document id, or None to mint a fresh one.
    """

    original_bytes: Annotated[bytes, FromParent()]
    filename: Annotated[str, FromParent()]
    doc_id: Annotated[str | None, FromParent(required=False)]


class IngestStageIngestStepContentAddressOutput(NodeOutput):
    """
    Output of the content-address step.

    Attributes:
        doc_id (str): The effective document id (pre-assigned or freshly minted).
        source_hash (str): The SHA-256 content address of the original bytes.
        original_format (str): The original file extension (lowercase, no dot).
        original_key (str): The object-store key the original was uploaded under.
    """

    doc_id: str
    source_hash: str
    original_format: str
    original_key: str


__all__ = [
    "IngestStageIngestStepContentAddressInput",
    "IngestStageIngestStepContentAddressOutput",
]
