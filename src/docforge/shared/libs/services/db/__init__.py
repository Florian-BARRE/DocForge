# ---------------------- The unified data layer ---------------------- #
from .database import Database

# ---------------------- Store clients (wired into Database at startup) ---------------------- #
from .postgresql import PostgresClient
from .qdrant import QdrantClient
from .s3 import S3Client

# ---------------------- Façade transfer objects ---------------------- #
from .facades import (
    CollectionFootprint,
    DocumentFootprint,
    IngestionPayload,
    IRBundle,
    PostgresFootprint,
    QdrantFootprint,
    S3Footprint,
)

# ------------------- Public API ------------------- #
__all__ = [
    "Database",
    "PostgresClient",
    "QdrantClient",
    "S3Client",
    "IngestionPayload",
    "IRBundle",
    "CollectionFootprint",
    "DocumentFootprint",
    "S3Footprint",
    "PostgresFootprint",
    "QdrantFootprint",
]
