# ====== Code Summary ======
# IngestPipeline — the concrete ingestion pipeline: a thin AbstractPipeline that declares only its
# identity (KEY/NAME/DESCRIPTION). All execution logic (topo order, the per-stage cache/track/
# error middleware, ON_ERROR dispatch, describe()) is inherited from AbstractPipeline. The stage
# set it runs is the registered ingest stages, assembled in topological order by
# assembly.stage_assembler.build_pipeline and handed to the constructor. This is the typed concrete
# pipeline the assembler/worker target; it does not change how stages are built — it only types and
# names the ingestion run.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import ClassVar

# ====== Internal Project Imports ======
from common_libs.pipeline.base.pipeline.core import AbstractPipeline


class IngestPipeline(AbstractPipeline):
    """
    Concrete ingest pipeline — identity only; the engine logic is inherited from AbstractPipeline.

    Assembles the registered ingest stages (ingest -> parse -> enrich -> chunk -> contextualize ->
    metagen -> embed/index), ordered by their ``AFTER`` edges. The stage list is built by the
    assembler and injected at construction; this class adds no behaviour over ``AbstractPipeline``.
    """

    KEY: ClassVar[str] = "ingest_pipeline"
    NAME: ClassVar[str] = "Ingest Pipeline"
    DESCRIPTION: ClassVar[str] = (
        "Document ingestion: ingest -> parse -> enrich -> chunk -> contextualize -> metagen "
        "-> embed/index."
    )


__all__ = ["IngestPipeline"]
