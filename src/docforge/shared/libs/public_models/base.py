# ====== Code Summary ======
# Base of the shared artefact vocabulary — the typed data that flows between pipeline nodes.
# A node's CONSUMES/PRODUCES faces reference these concrete artefact classes (DocumentIR,
# ChunkSet, …). The graph validator decides producer→consumer compatibility by a plain subclass
# relationship over them, so keeping every artefact under one base keeps that check honest.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, ConfigDict


class Artifact(BaseModel):
    """
    Base class for every shared data artefact exchanged between nodes.

    Concrete artefacts subclass this and live alongside it in shared/libs/public_models. They
    are referenced by node I/O faces and compared by subclass relationship during graph
    validation.
    """


class NodeConfig(BaseModel):
    """
    Base class for a node's CONFIG face (the serialized, UI-editable knobs).

    Lives in public_models (the bottom vocabulary layer) so config value-objects that are also
    embedded in artefacts (e.g. OpenAICompatConfig, carried by a GenerationRequest) need no
    upward import into the pipelines layer.

    extra="forbid" is the point: a typo in a stored pipeline blob ("do_ocrr") must fail the build
    loudly instead of being silently ignored — a config the user believes is set MUST be applied.
    """

    model_config = ConfigDict(extra="forbid")


__all__ = ["Artifact", "NodeConfig"]
