# ====== Code Summary ======
# Defines the shared application context (typed service locator) used across all routes and the
# lifespan. Type annotations only — all values are assigned at startup in entrypoint.py or
# lifespan.py. Access via CONTEXT.attribute_name anywhere in the codebase.

# ====== Standard Library Imports ======
from typing import Type

# ====== Internal Project Imports ======
from config_loader import BgeServerConfig
from libs.bge_models import BgeModelsService


class CONTEXT:
    """
    Shared application context for the BGE model-suite micro-service.

    A typed static service locator — never instantiated. All attributes are set during
    startup (entrypoint.py injects config; lifespan.py injects the loaded model service).
    """

    # ── Configuration ────────────────────────────────────────────────────────────
    CONFIG: Type[BgeServerConfig]

    # ── Model service ─────────────────────────────────────────────────────────────
    # Holds the loaded BGE embed + rerank models after lifespan startup completes.
    bge_models: BgeModelsService
