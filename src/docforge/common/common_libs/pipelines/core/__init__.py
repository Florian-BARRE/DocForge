# The v1 concrete pipelines (IngestPipeline + the v1 stage/step node tree) are deleted — ingestion
# now runs on the flow engine (common_libs.pipelines.flow + the stage packages). What survives under
# core/ is the REUSED pure domain logic the flow nodes import directly (the enrich helpers, the
# structure-aware chunker, the parse helpers) + the per-stage Config classes consumed by the builder.
