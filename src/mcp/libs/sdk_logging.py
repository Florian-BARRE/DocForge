# ====== Code Summary ======
# Routes the mcp SDK's standard-library logging (the `mcp` logger tree: mcp.server.mcpserver.*,
# mcp.server.streamable_http, ...) into loggerplusplus, so the SDK's own records — a tool call
# rejected on its arguments, a tool that failed or crashed — come out through the service's sinks
# and format, at their own level. Without it they go to the root RichHandler the SDK installs
# (MCPServer.__init__ -> configure_logging), in another format and outside the file sink.

from __future__ import annotations

# ====== Standard Library Imports ======
import logging

# ====== Third-Party Library Imports ======
from loggerplusplus import InterceptHandler, intercept_std_logging

# Root of the SDK's logger names (every SDK module logs through logging.getLogger(__name__)).
SDK_LOGGER = "mcp"


def route_sdk_logging() -> InterceptHandler:
    """
    Send the mcp SDK's logging records to loggerplusplus, once each.

    The `mcp` logger gets the intercept handler as its only handler and stops propagating, so the
    root handler the SDK installs never prints a second copy. Its level is DEBUG: the loguru sinks
    (LOGGING_CONSOLE_LEVEL, LOGGING_FILE_LEVEL) decide what is shown, not the root's WARNING.
    Each record keeps its level and is labelled with its logger name. Idempotent.

    Returns:
        InterceptHandler: The installed handler.
    """
    return intercept_std_logging(logging.DEBUG, modules=[SDK_LOGGER])


__all__ = ["SDK_LOGGER", "route_sdk_logging"]
