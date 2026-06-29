# ---------------------- Assemble-doc-meta step --------------- #
from .core import IngestStageMetagenStepAssembleDocMeta
from .context import IngestStageMetagenStepAssembleDocMetaContext
from .errors import IngestStageMetagenStepAssembleDocMetaError
from .io import (
    IngestStageMetagenStepAssembleDocMetaInput,
    IngestStageMetagenStepAssembleDocMetaOutput,
)

# ---------------------- Public API --------------------------- #
__all__ = [
    "IngestStageMetagenStepAssembleDocMeta",
    "IngestStageMetagenStepAssembleDocMetaContext",
    "IngestStageMetagenStepAssembleDocMetaError",
    "IngestStageMetagenStepAssembleDocMetaInput",
    "IngestStageMetagenStepAssembleDocMetaOutput",
]
