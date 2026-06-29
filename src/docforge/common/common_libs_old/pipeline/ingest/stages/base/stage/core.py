# ====== Code Summary ======
# IngestStage — the ingest-typology specialization of the universal AbstractStage contract. It
# is a THIN abstract base (no executive logic): the whole run/track/fingerprint/describe template
# is inherited from AbstractStage. Its only role is to mark the ingestion family of stages and to
# give them a common home so the registry can discover them under pipeline/ingest/stages/. Concrete
# ingest stages (ParsingStage, ...) subclass this and DECLARE their forced ClassVars + steps.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Internal Project Imports ======
from common_libs.pipeline.base.stage.core import AbstractStage


class IngestStage(AbstractStage, abstract=True):
    """
    Ingest-family stage contract — a thin specialization of ``AbstractStage``.

    Carries no executive logic: a concrete ingest stage inherits the entire run/track/fingerprint/
    describe machinery from ``AbstractStage`` and only declares its identity, ordering, IO, cache
    policy, error policy (the forced ClassVars) and its ordered ``steps``. This base exists purely
    to type the ingestion family and to anchor the ``pipeline/ingest/stages/`` package the stage
    registry discovers. It is ``abstract=True`` so it skips the forced-ClassVar check.
    """


__all__ = ["IngestStage"]
