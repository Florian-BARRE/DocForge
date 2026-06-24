# ====== Code Summary ======
# MetadataFieldsResponse: API response model returning the system metadata field catalog.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel

# ====== Local Project Imports ======
from .meta_field_spec import MetaFieldSpec


class MetadataFieldsResponse(BaseModel):
    """System metadata field catalog (the always-present, auto-extracted fields)."""

    system_fields: list[MetaFieldSpec]
