# ====== Code Summary ======
# LoggingBootstrap: configures the loggerplusplus sinks of a model-host micro-service from its
# ServerConfig. It reproduces the bootstrap every server used to repeat in config_loader.py: drop the
# default sink, flash a DEV MODE warning on a temporary debug sink when DEV_MODE is on, then add the
# console and the rotating file sinks the configuration asks for.

# ====== Standard Library Imports ======
from __future__ import annotations

import pathlib
import sys
from typing import Final

# ====== Third-Party Library Imports ======
from loggerplusplus import formats as lpp_formats
from loggerplusplus import loggerplusplus

# ====== Local Project Imports ======
from .server_config import ServerConfig

# ====== Constants ======
# loguru treats this as a file path (a file named `logs`, rotated weekly), as every server did.
_FILE_SINK_PATH: Final[pathlib.Path] = pathlib.Path("logs")


class LoggingBootstrap:
    """Applies the logging section of a `ServerConfig` to the global loggerplusplus sinks.

    Args:
        config (type[ServerConfig]): The injected configuration (only its DEV_MODE and LOGGING_*
            attributes are read).
    """

    # Private attributes
    _config: type[ServerConfig]

    def __init__(self, config: type[ServerConfig]) -> None:
        self._config = config

    # =======================
    #   Private Methods
    # =======================
    def _build_format(self) -> lpp_formats.ShortFormat:
        """Instantiate the loggerplusplus format named by the configuration.

        Returns:
            lpp_formats.ShortFormat: The named format, or `ShortFormat` when the name is unknown.
        """
        format_cls = getattr(lpp_formats, self._config.LOGGING_LPP_FORMAT, lpp_formats.ShortFormat)
        built: lpp_formats.ShortFormat = format_cls()
        return built

    def _flash_dev_mode_warning(self) -> None:
        """Print the DEV MODE warning on a temporary debug sink, then remove that sink."""
        loggerplusplus.add(sink=sys.stdout, level="DEBUG", format=lpp_formats.ShortFormat())
        loggerplusplus.bind(identifier="DEV").warning("DEV MODE is activated !")
        loggerplusplus.remove()

    # =======================
    #   Public Methods
    # =======================
    def apply(self) -> None:
        """Reset the global sinks and add the ones the configuration asks for."""
        # 1. Reset, so the library's default sink never double-logs.
        loggerplusplus.remove()

        # 2. DEV_MODE announces itself before the real sinks exist (a debug sink, used once).
        if self._config.DEV_MODE:
            self._flash_dev_mode_warning()

        # 3. The real sinks.
        log_format = self._build_format()
        if self._config.LOGGING_ENABLE_CONSOLE:
            loggerplusplus.add(
                sink=sys.stdout, level=self._config.LOGGING_CONSOLE_LEVEL, format=log_format
            )
        if self._config.LOGGING_ENABLE_FILE:
            loggerplusplus.add(
                _FILE_SINK_PATH,
                level=self._config.LOGGING_FILE_LEVEL,
                format=log_format,
                rotation="1 week",
                retention="30 days",
                compression="zip",
                encoding="utf-8",
                enqueue=True,
                backtrace=True,
                diagnose=False,
            )
