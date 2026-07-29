# --------------------- Facade --------------------- #
from .client import DocForgeClient

# ------------------- Transport -------------------- #
from .transport import DocForgeTransport

# ------------------- Sub-APIs --------------------- #
from .auth import AuthApi
from .blobs import BlobsApi
from .collections import CollectionsApi
from .documents import DocumentsApi
from .explorer import ExplorerApi
from .health import HealthApi
from .jobs import JobsApi
from .pipelines import PipelinesApi
from .search import SearchApi

# ------------------- Public API ------------------- #
__all__ = [
    "DocForgeClient",
    "DocForgeTransport",
    "AuthApi",
    "BlobsApi",
    "CollectionsApi",
    "DocumentsApi",
    "ExplorerApi",
    "HealthApi",
    "JobsApi",
    "PipelinesApi",
    "SearchApi",
]
