# ====== Code Summary ======
# Defines the shared application context (typed service locator) used across all routes and the
# lifespan. Type annotations only — all values are assigned at startup in entrypoint.py or
# lifespan.py. Access via CONTEXT.attribute_name anywhere in the codebase.

# ====== Standard Library Imports ======

# ====== Internal Project Imports ======
from config_loader import BgeServerConfig
from libs.batching import BatchingEngine
from libs.bge_models import BgeModelsService


class CONTEXT:
    """
    Shared application context for the BGE model-suite micro-service.

    A typed static service locator — never instantiated. All attributes are set during
    startup (entrypoint.py injects config; lifespan.py injects the loaded model service
    and the batching engine).
    """

    # ── Configuration ────────────────────────────────────────────────────────────
    CONFIG: type[BgeServerConfig]

    # ── Model service ─────────────────────────────────────────────────────────────
    # Holds the loaded BGE embed + rerank models after lifespan startup completes.
    bge_models: BgeModelsService

    # ── Dynamic batching engine ───────────────────────────────────────────────────
    # Owns four BatchQueueWorkers (dense / sparse / colbert / rerank) plus TWO asyncio.Locks:
    # embed_lock (dense/sparse/colbert, which share one embed_model instance) and rerank_lock
    # (the separate FlagReranker instance). Routes submit to the engine rather than calling
    # the model service directly — the engine handles batching, locking, to_thread, and scatter.
    # Created and started in lifespan.py after models are loaded. Stopped in the finally
    # block before models are unloaded.
    batching_engine: BatchingEngine
