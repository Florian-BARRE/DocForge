# ====== Code Summary ======
# Defines the shared application context (typed service locator) used across all routes and the
# lifespan. Type annotations only — all values are assigned at startup in entrypoint.py or lifespan.py.
# Access via CONTEXT.attribute_name anywhere in the codebase.

# ====== Internal Project Imports ======
from config_loader import MineruServerConfig
from libs.mineru import MineruService


class CONTEXT:
    """
    Shared application context for the MinerU2.5-Pro VLM parse micro-service.

    A typed static service locator — never instantiated. All attributes are set during startup
    (entrypoint.py injects config + the service; lifespan.py validates config).
    """

    # ── Configuration ────────────────────────────────────────────────────────────
    CONFIG: type[MineruServerConfig]

    # ── MinerU parse service ─────────────────────────────────────────────────────
    # Holds the MinerU2.5-Pro VLM parse pipeline. The heavy model loads LAZILY inside the engine on the
    # first /parse request (not at lifespan startup), so a deployment that never escalates to this
    # parser never pays the model download/load. Owns the asyncio.Lock that serializes every parse.
    mineru: MineruService
