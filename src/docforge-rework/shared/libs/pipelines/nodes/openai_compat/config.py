# ====== Code Summary ======
# Re-export of OpenAICompatConfig for the pipelines layer. The class itself now lives in the shared
# vocabulary (shared_libs.public_models.endpoint) because it is pure endpoint data that both node
# configs AND artefacts reference (a GenerationRequest carries its endpoint) — keeping the definition
# under this node package would force public_models to import the node-family package and cycle at
# import. Every existing consumer keeps importing ``OpenAICompatConfig`` from here unchanged; only
# its definition site moved.

# ====== Internal Project Imports ======
from shared_libs.public_models.endpoint import OpenAICompatConfig

__all__ = ["OpenAICompatConfig"]
