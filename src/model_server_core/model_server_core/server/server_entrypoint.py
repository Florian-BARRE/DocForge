# ====== Code Summary ======
# ServerEntrypoint: the thin helper that makes a server's entrypoint.py "build the config, hand it to a
# ModelServer, run", with zero logic of its own. It applies the logging bootstrap, builds the ASGI app
# (exposed as `app` for `uvicorn entrypoint:app`) and can run uvicorn itself from the configured
# host and port.

# ====== Standard Library Imports ======
from __future__ import annotations

from collections.abc import Callable
from typing import Generic

# ====== Third-Party Library Imports ======
import uvicorn
from fastapi import FastAPI
from loggerplusplus import LoggerClass

# ====== Internal Project Imports ======
from model_server_core.config import LoggingBootstrap

# ====== Local Project Imports ======
from .model_server import ConfigT, ModelServer


class ServerEntrypoint(LoggerClass, Generic[ConfigT]):
    """Binds a `ModelServer` to its ASGI app and to uvicorn.

    Typical `entrypoint.py` of a server::

        entrypoint = ServerEntrypoint(PaddleServer(PaddleServerConfig))
        app = entrypoint.app

        if __name__ == "__main__":
            entrypoint.run()

    Args:
        server (ModelServer[ConfigT]): The server to assemble.
        runner (Callable[..., None]): The function that serves an ASGI app (`uvicorn.run`); injected
            so tests do not open a socket.
    """

    # Public attributes
    server: ModelServer[ConfigT]
    app: FastAPI

    # Private attributes
    _runner: Callable[..., None]

    def __init__(
        self, server: ModelServer[ConfigT], *, runner: Callable[..., None] = uvicorn.run
    ) -> None:
        LoggerClass.__init__(self)
        self.server = server
        self._runner = runner

        # 1. Sinks first, so the app assembly below is already logged the way the config asks.
        LoggingBootstrap(server.config).apply()

        # 2. Assemble the app once.
        self.app = server.create_app()

    def run(self) -> None:
        """Serve the app on the configured host and port (blocking)."""
        host, port = self.server.config.SERVER_HOST, self.server.config.SERVER_PORT
        self.logger.info(f"START serving {self.server.title} (host={host}, port={port})")
        self._runner(self.app, host=host, port=port)
