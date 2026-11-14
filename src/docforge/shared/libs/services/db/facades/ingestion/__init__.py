# ====== Code Summary ======
# Split of the ingestion façade by responsibility. ``IngestionFacade`` (ingestion/ingestion_facade.py)
# is the public surface behind ``Database.ingestion`` and delegates to IngestionAdmission (admit,
# reingest, dedup), IngestionPersister (blobs, save, status marks), TracePayloadStore (full trace
# payloads) and IngestionIndexer (Qdrant indexing); import the façade, not those internal
# collaborators, from outside.

from .ingestion_facade import IngestionFacade

__all__ = ["IngestionFacade"]
