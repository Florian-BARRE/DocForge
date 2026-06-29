# ---------------------- Concrete pipelines (scaffolding) ----- #
# Each concrete pipeline is a package mirroring the node quad (core / context / errors / io) and a
# stages/ subtree. Populated as pipelines are built:
#   ingest/   the document ingestion pipeline (ingest -> parse -> enrich -> chunk -> ...)
#   search/   the query pipeline (query-transform -> retrieve -> rerank)

# ---------------------- Public API --------------------------- #
__all__: list[str] = []
