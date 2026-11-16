# ====== Code Summary ======
# Test seam shared by the bge_server tests: builds the real BgeServer (no lifespan, so no model load)
# and swaps its engine and model service for fakes, so a route, /health or the whole app can be
# driven through a TestClient without torch or FlagEmbedding.

# ====== Standard Library Imports ======
from typing import Any

# ====== Internal Project Imports ======
from backend import BgeServer
from config_loader import BgeServerConfig


def build_server(
    engine: Any | None = None,
    models: Any | None = None,
    config: type[BgeServerConfig] = BgeServerConfig,
) -> BgeServer:
    """Assemble a BgeServer whose engine and models are the given fakes.

    Args:
        engine (Any | None): Fake batching engine the routes submit to (None: not started).
        models (Any | None): Fake model service (None: the real, unloaded one).
        config (type[BgeServerConfig]): The configuration to inject.

    Returns:
        BgeServer: The server; call `create_app()` on it.
    """
    server = BgeServer(config)
    if engine is not None:
        server.runtime.engine = engine
    if models is not None:
        server.models = models
        server.runtime.models = models
    return server
