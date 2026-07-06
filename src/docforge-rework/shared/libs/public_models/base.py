# ====== Code Summary ======
# Base of the shared artefact vocabulary — the typed data that flows between pipeline nodes.
# A node's CONSUMES/PRODUCES faces reference these concrete artefact classes (DocumentIR,
# ChunkSet, …). The graph validator decides producer→consumer compatibility by a plain subclass
# relationship over them, so keeping every artefact under one base keeps that check honest.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel


class Artifact(BaseModel):
    """
    Base class for every shared data artefact exchanged between nodes.

    Concrete artefacts subclass this and live alongside it in shared/libs/public_models. They
    are referenced by node I/O faces and compared by subclass relationship during graph
    validation.
    """


__all__ = ["Artifact"]
