# The v1 stage node classes (IngestStage*) are deleted — the flow stage packages
# (common_libs.pipelines.{ingest,parse,enrich,chunk,contextualize,metagen,embed_index}) replace them.
# Each stage folder here now only keeps its REUSED pure helpers + its per-stage Config class, imported
# by full module path (e.g. core.ingest.stages.enrich.ir_builder, core.ingest.stages.chunk.config).
