# ====== Code Summary ======
# The reserved Qdrant payload keys — the point's OWN machinery: document identity, chunk ordinal,
# searchability flag. A filterable metadata field is denormalised onto the point BY NAME, so a field
# sharing one of these would overwrite it and corrupt search / deletion-by-document. Defined once
# here and imported everywhere these keys are written (translator), filtered (search facade),
# patched (enablement facade), indexed (collection api) or guarded against (collections router).

# The individual keys — used where a single bare literal would otherwise be written.
DOCUMENT_ID_KEY = "document_id"
CHUNK_INDEX_KEY = "chunk_index"
ENABLED_KEY = "enabled"

# The full set — used by the router guard that rejects a metadata field shadowing any of them.
RESERVED_PAYLOAD_KEYS = frozenset({DOCUMENT_ID_KEY, CHUNK_INDEX_KEY, ENABLED_KEY})


__all__ = ["DOCUMENT_ID_KEY", "CHUNK_INDEX_KEY", "ENABLED_KEY", "RESERVED_PAYLOAD_KEYS"]
