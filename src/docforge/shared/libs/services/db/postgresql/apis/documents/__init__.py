# ====== Code Summary ======
# Split of the document data-access API by responsibility. ``DocumentApi`` (apis/document_api.py)
# stays the public facade and delegates to these classes; import the facade, not these units, from
# outside.

from .document_metadata_api import DocumentMetadataApi
from .document_page_api import DocumentPageApi
from .document_row_api import DocumentRowApi

__all__ = ["DocumentMetadataApi", "DocumentPageApi", "DocumentRowApi"]
