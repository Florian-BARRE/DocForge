# ====== Code Summary ======
# Request/response models for the collections resource, mirrored field-for-field from the DocForge
# backend router models. The classes live in sub-modules by concern (the contract and its CRUD bodies,
# bulk re-ingest, description) and are re-exported here, so ``docforge_sdk.models.collections`` stays the
# import path it always was.

# ====== Local Project Imports ======
from .._reexport import pin_module_path
from .._shared import FieldOrigin as FieldOrigin
from .._shared import FieldScope as FieldScope
from .._shared import FieldType as FieldType
from ..estimate import EstimateOverrides as EstimateOverrides
from ..field_spec import FieldSpec as FieldSpec
from ..health import CollectionHealthSummary as CollectionHealthSummary
from ..reingest import ReingestJobHandle as ReingestJobHandle
from ..schema_ops import FieldOp as FieldOp
from ..schema_ops import SchemaDiff as SchemaDiff
from .bulk_reingest import BulkReingestAccepted, BulkReingestRequest
from .collection import (
    CollectionListItem,
    CollectionModel,
    CreateCollectionRequest,
    UpdateCollectionRequest,
    UpdateCollectionResponse,
)
from .description import (
    CollectionContractSchemaResponse,
    CollectionDescription,
    FieldGuide,
    SearchTargetGuide,
)

# ------------------- Public API ------------------- #
__all__ = [
    "FieldSpec",
    "CollectionModel",
    "CollectionListItem",
    "CreateCollectionRequest",
    "UpdateCollectionRequest",
    "UpdateCollectionResponse",
    "BulkReingestRequest",
    "ReingestJobHandle",
    "BulkReingestAccepted",
    "CollectionContractSchemaResponse",
    "FieldGuide",
    "SearchTargetGuide",
    "CollectionDescription",
]

# Keep every class importable at (and reporting) its pre-split path, ``docforge_sdk.models.collections``.
pin_module_path(__name__, globals(), __all__)
