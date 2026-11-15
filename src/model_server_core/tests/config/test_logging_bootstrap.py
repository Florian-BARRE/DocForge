# ====== Code Summary ======
# Behaviour of LoggingBootstrap: which sinks the configuration produces (console, file, DEV_MODE flash,
# format fallback), observed through the output they emit.

# ====== Standard Library Imports ======
import pathlib

# ====== Third-Party Library Imports ======
import pytest
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from model_server_core import LoggingBootstrap, ServerConfig


def _config(**overrides: object) -> type[ServerConfig]:
    return type("LoggingConfig", (ServerConfig,), overrides)


def test_console_sink_receives_records_at_the_configured_level(
    capsys: pytest.CaptureFixture[str],
) -> None:
    LoggingBootstrap(_config(LOGGING_CONSOLE_LEVEL="WARNING")).apply()

    logger = loggerplusplus.bind(identifier="Probe")
    logger.info("quiet info")
    logger.warning("loud warning")

    out = capsys.readouterr().out
    assert "loud warning" in out
    assert "quiet info" not in out


def test_console_disabled_emits_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    LoggingBootstrap(_config(LOGGING_ENABLE_CONSOLE=False)).apply()

    loggerplusplus.bind(identifier="Probe").error("should vanish")

    assert capsys.readouterr().out == ""


def test_dev_mode_flashes_a_warning_on_a_temporary_sink(
    capsys: pytest.CaptureFixture[str],
) -> None:
    LoggingBootstrap(_config(DEV_MODE=True)).apply()

    first = capsys.readouterr().out
    assert "DEV MODE is activated" in first

    # The temporary sink is gone: only the console sink (INFO) remains, so DEBUG stays silent.
    loggerplusplus.bind(identifier="Probe").debug("debug after bootstrap")
    assert "debug after bootstrap" not in capsys.readouterr().out


def test_unknown_format_name_falls_back_to_the_short_format(
    capsys: pytest.CaptureFixture[str],
) -> None:
    LoggingBootstrap(_config(LOGGING_LPP_FORMAT="NoSuchFormat")).apply()

    loggerplusplus.bind(identifier="Probe").info("still logged")

    assert "still logged" in capsys.readouterr().out


def test_file_sink_writes_the_logs_file_in_the_working_directory(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    LoggingBootstrap(_config(LOGGING_ENABLE_CONSOLE=False, LOGGING_ENABLE_FILE=True)).apply()

    loggerplusplus.bind(identifier="Probe").info("to the file")
    loggerplusplus.remove()  # flushes the enqueued file sink

    assert "to the file" in (tmp_path / "logs").read_text()
