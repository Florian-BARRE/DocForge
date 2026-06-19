# ------------------- Base ------------------- #
from .base import Base

# ------------------- Models ------------------- #
# Every model module MUST be imported here so all tables register on
# Base.metadata. Alembic autogenerate and migrations/env.py rely on this
# import being complete to discover the full schema.
from .block import BlockModel
from .collection import CollectionModel
from .config_version import ConfigVersionModel
from .document import DocumentModel
from .job import JobModel
from .metadata_field import MetadataFieldModel
from .provider_call import ProviderCallModel
from .stage_run import StageRunModel

# ------------------- Public API ------------------- #
__all__ = [
    "Base",
    "BlockModel",
    "CollectionModel",
    "ConfigVersionModel",
    "DocumentModel",
    "JobModel",
    "MetadataFieldModel",
    "ProviderCallModel",
    "StageRunModel",
]
