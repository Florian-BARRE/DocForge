# ====== Code Summary ======
# MetaFieldType: the set of allowed types for a metadata field (spec §3 MetaField.type).

# ====== Standard Library Imports ======
from typing import Literal

# MetaFieldType is a Literal type alias (not an enum) — kept as a module-level alias
# per project convention for Literal types in Pydantic models.
MetaFieldType = Literal["string", "number", "date", "bool", "enum", "string[]"]
