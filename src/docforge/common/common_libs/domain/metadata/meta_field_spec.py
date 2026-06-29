# ====== Code Summary ======
# MetaFieldSpec: Pydantic model for a metadata field definition (spec §3 MetaField, §7.2).
# Defines the three orthogonal search roles (filterable / lexical / semantic) and their
# RRF fusion weights for the DocForge retrieval system.

# ====== Standard Library Imports ======
from typing import Literal

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict, Field

# ====== Local Project Imports ======
from .meta_field_type import MetaFieldType


class MetaFieldSpec(BaseModel):
    """
    A metadata field definition (spec §3 MetaField, §7.2 three orthogonal capabilities).

    Three independent search roles + RRF fusion weights:
    - filterable → indexed Qdrant payload (exact/range filter)
    - lexical    → dedicated BM25 sparse vector (keyword match)
    - semantic   → dedicated named dense vector (fuzzy/semantic match)
    """

    model_config = ConfigDict(from_attributes=True)

    field_name: str = Field(..., min_length=1, max_length=255)
    field_type: MetaFieldType = "string"
    required: bool = False
    filterable: bool = False
    lexical: bool = False
    semantic: bool = False
    enum_values: list[str] | None = None
    is_system: bool = False
    # Field provenance — 'system' (pipeline-extracted), 'user' (caller-authored, uploaded values),
    # 'generated' (caller-authored, values produced by S5b at ingestion). Defaults to 'user'; system
    # fields are forced to 'system' in system_fields.py.
    origin: Literal["system", "user", "generated"] = "user"
