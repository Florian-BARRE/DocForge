# ====== Code Summary ======
# Offline schema-parity guard: every SDK model that mirrors a backend router model must agree with the
# live API's OpenAPI schema (committed as tests/openapi_snapshot.json) on property names and required
# fields. The mapping is keyed by the OpenAPI schema name (which differs from a few SDK class names,
# e.g. FieldSpec ↔ FieldSpecModel). Models with no 1:1 API schema (list wrappers, opaque-blob
# envelopes rendered as raw bytes, SDK-only wrappers) are skipped with an explicit reason.

# ====== Standard Library Imports ======
import json
from pathlib import Path
from typing import Any

# ====== Third-Party Library Imports ======
import pytest
from pydantic import BaseModel

# ====== Local Project Imports ======
from docforge_sdk.models.auth import CreatedKey, CreateKeyRequest, KeyInfo, RotateKeyRequest
from docforge_sdk.models.collections import (
    CollectionModel,
    CreateCollectionRequest,
    FieldSpec,
    UpdateCollectionRequest,
)
from docforge_sdk.models.documents import DocumentEnabledResponse, EnabledPatch, UploadAccepted
from docforge_sdk.models.explorer import (
    BulkChunkEnabledPatch,
    BulkChunkEnabledResponse,
    ChunkEnabledPatch,
    ChunkEnabledResult,
    ChunkInfo,
    DocumentDetail,
    DocumentListItem,
    MetadataValue,
    PageInfo,
)
from docforge_sdk.models.ir import DocumentIRModel, IRBlock, IREnrichment, IRFigure, IRTable
from docforge_sdk.models.jobs import JobEvent, JobStatus, JobTrace, WorkerActivity, WorkersLive
from docforge_sdk.models.pipelines import (
    EditResponse,
    InspectResponse,
    PipelineDesignResponse,
    PipelineIndexResponse,
    PipelineSurface,
    StageApplyResponse,
    StageViewResponse,
)
from docforge_sdk.models.search import SearchHit, SearchRequest, SearchResponse, SearchTarget

_SNAPSHOT = Path(__file__).resolve().parents[1] / "openapi_snapshot.json"

# Maps the OpenAPI component-schema NAME to the SDK model that mirrors it. A handful of SDK classes
# drop the backend's "Model" suffix (FieldSpec, SearchTarget, SearchHit), so the key is authoritative.
_MODELS: dict[str, type[BaseModel]] = {
    # Auth
    "CreateKeyRequest": CreateKeyRequest,
    "RotateKeyRequest": RotateKeyRequest,
    "CreatedKey": CreatedKey,
    "KeyInfo": KeyInfo,
    # Collections
    "FieldSpecModel": FieldSpec,
    "CollectionModel": CollectionModel,
    "CreateCollectionRequest": CreateCollectionRequest,
    "UpdateCollectionRequest": UpdateCollectionRequest,
    # Documents
    "UploadAccepted": UploadAccepted,
    "EnabledPatch": EnabledPatch,
    "DocumentEnabledResponse": DocumentEnabledResponse,
    # Explorer
    "MetadataValue": MetadataValue,
    "DocumentListItem": DocumentListItem,
    "DocumentDetail": DocumentDetail,
    "PageInfo": PageInfo,
    "ChunkInfo": ChunkInfo,
    "ChunkEnabledPatch": ChunkEnabledPatch,
    "BulkChunkEnabledPatch": BulkChunkEnabledPatch,
    "ChunkEnabledResult": ChunkEnabledResult,
    "BulkChunkEnabledResponse": BulkChunkEnabledResponse,
    # IR
    "IRBlock": IRBlock,
    "IRTable": IRTable,
    "IRFigure": IRFigure,
    "IREnrichment": IREnrichment,
    "DocumentIRModel": DocumentIRModel,
    # Search
    "SearchTargetModel": SearchTarget,
    "SearchRequest": SearchRequest,
    "SearchHitModel": SearchHit,
    "SearchResponse": SearchResponse,
    # Jobs
    "JobStatus": JobStatus,
    "JobEvent": JobEvent,
    "JobTrace": JobTrace,
    "WorkerActivity": WorkerActivity,
    "WorkersLive": WorkersLive,
    # Pipelines (opaque graph JSON typed as dicts, but property names + required still 1:1)
    "PipelineSurface": PipelineSurface,
    "PipelineIndexResponse": PipelineIndexResponse,
    "PipelineDesignResponse": PipelineDesignResponse,
    "InspectResponse": InspectResponse,
    "EditResponse": EditResponse,
    "StageViewResponse": StageViewResponse,
    "StageApplyResponse": StageApplyResponse,
}

# SDK models deliberately WITHOUT a 1:1 OpenAPI schema, each with the reason it is skipped.
_SKIPPED: dict[str, str] = {
    "HealthStatus": "health route is registered with include_in_schema=False (absent from the schema).",
    "BlobContent": "SDK-only wrapper — the blobs endpoint streams raw bytes, not a JSON schema.",
}


def _schemas() -> dict[str, Any]:
    """Load the committed OpenAPI component schemas, or skip when the snapshot is missing."""
    if not _SNAPSHOT.exists():
        pytest.skip("OpenAPI snapshot not available — skipping model/API parity check.")
    spec = json.loads(_SNAPSHOT.read_text())
    return spec["components"]["schemas"]


@pytest.mark.parametrize("name", list(_MODELS))
def test_property_names_match_api(name: str) -> None:
    api = _schemas()[name]
    sdk = _MODELS[name].model_json_schema()
    assert set(sdk["properties"]) == set(api["properties"]), name


@pytest.mark.parametrize("name", list(_MODELS))
def test_required_fields_match_api(name: str) -> None:
    api = _schemas()[name]
    sdk = _MODELS[name].model_json_schema()
    assert set(sdk.get("required", [])) == set(api.get("required", [])), name


@pytest.mark.parametrize("name", list(_SKIPPED))
def test_skipped_models_have_a_reason(name: str) -> None:
    # Documents WHY a model is exempt from the API-parity diff so the exemption is explicit, not silent.
    assert _SKIPPED[name]
