# ====== Code Summary ======
# IngestStep — the ingest-typology specialization of the universal AbstractStep contract, plus the
# IngestChainStep alias for the chain-backed variant. Both are THIN: they add no logic over
# AbstractStep / ChainStep. Their role is to mark the ingestion family of steps and to give native
# ingest stages a typed step base under pipeline/ingest/stages/. A concrete ingest step (ParseStep,
# ...) subclasses IngestStep and implements run(); chain-backed ingest steps use IngestChainStep.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Internal Project Imports ======
from common_libs.pipeline.base.step.core import AbstractStep, ChainStep


class IngestStep(AbstractStep):
    """
    Ingest-family step contract — a thin specialization of ``AbstractStep``.

    Adds no behaviour over ``AbstractStep``: it exists to type the ingestion family of steps and
    to anchor them under ``pipeline/ingest/stages/``. Concrete ingest steps subclass this and
    implement ``run(ctx)``; identity/IO are carried as ClassVars (or per-instance properties).
    """


# Chain-backed ingest steps reuse the universal ChainStep verbatim; the alias keeps ingest stages
# importing their step bases from one ingest-local module rather than reaching into base/step.
IngestChainStep = ChainStep


__all__ = ["IngestStep", "IngestChainStep"]
