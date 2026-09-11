# ====== Code Summary ======
# The preview feature's typed faults. A PreviewGraphError is the "the blob is structurally wrong"
# failure (the router maps it to a 422, exactly like search): an unbuildable/invalid candidate blob
# or a final output that is not an ingestion RunBundle. A PreviewInputError is a caller-input fault
# (neither a file nor a document id supplied, an unknown document, an oversized body) — also a 422.
# A run that BUILT fine but a node failed is NOT an error here: it is DATA returned in the response
# (ok=false + the partial trace showing where it died), never raised.


class PreviewGraphError(Exception):
    """Raised when the pipeline blob to preview does not build/validate or is not an ingestion graph."""


class PreviewInputError(Exception):
    """Raised on a caller-input fault: no source supplied, unknown document, or oversized body."""


__all__ = ["PreviewGraphError", "PreviewInputError"]
