# ---------------------- The unified data layer ---------------------- #
from .database import Database

# ---------------------- Store clients (wired into Database at startup) ---------------------- #
from .postgresql import PostgresClient
from .qdrant import QdrantClient
from .s3 import S3Client

# ---------------------- Façade transfer objects ---------------------- #
from .facades import IngestionPayload, IRBundle, SearchHit

# ------------------- Public API ------------------- #
__all__ = [
    "Database",
    "PostgresClient",
    "QdrantClient",
    "S3Client",
    "IngestionPayload",
    "IRBundle",
    "SearchHit",
]
