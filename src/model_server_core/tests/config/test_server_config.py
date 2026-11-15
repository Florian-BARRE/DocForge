# ====== Code Summary ======
# Behaviour of ServerConfig: environment defaults and overrides (the class body reads the environment
# once, so the module is reloaded under a controlled environment), subclass extension, and the
# fail-fast validate().

# ====== Standard Library Imports ======
import importlib
from collections.abc import Callable, Iterator

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from model_server_core import ServerConfig
from model_server_core.config import server_config as server_config_module

ReloadConfig = Callable[..., type[ServerConfig]]

_BASE_VARIABLES = (
    "DEV_MODE",
    "LOGGING_CONSOLE_LEVEL",
    "LOGGING_FILE_LEVEL",
    "LOGGING_ENABLE_CONSOLE",
    "LOGGING_ENABLE_FILE",
    "LOGGING_LPP_FORMAT",
    "SERVER_HOST",
    "SERVER_PORT",
    "MAX_BODY_BYTES",
    "LOCK_WAIT_TIMEOUT_SECONDS",
    "GZIP_MINIMUM_SIZE",
    "DEVICE",
    "NUM_THREADS",
)


@pytest.fixture
def reload_config(monkeypatch: pytest.MonkeyPatch) -> Iterator[ReloadConfig]:
    """Return a function that re-evaluates ServerConfig under the given environment."""
    for name in _BASE_VARIABLES:
        monkeypatch.delenv(name, raising=False)

    def _reload(**environment: str) -> type[ServerConfig]:
        for name, value in environment.items():
            monkeypatch.setenv(name, value)
        reloaded: type[ServerConfig] = importlib.reload(server_config_module).ServerConfig
        return reloaded

    yield _reload

    # The environment is restored by monkeypatch AFTER this fixture body; re-evaluate the pristine class.
    monkeypatch.undo()
    importlib.reload(server_config_module)


def test_defaults_without_environment(reload_config: ReloadConfig) -> None:
    config = reload_config()

    assert config.DEV_MODE is False
    assert config.SERVER_HOST == "0.0.0.0"
    assert config.SERVER_PORT == 80
    assert config.MAX_BODY_BYTES == 104_857_600
    assert config.LOCK_WAIT_TIMEOUT_SECONDS == 290.0
    assert config.GZIP_MINIMUM_SIZE == 1024
    assert config.DEVICE == "auto"
    assert config.NUM_THREADS == 0
    assert config.LOGGING_ENABLE_CONSOLE is True
    assert config.LOGGING_ENABLE_FILE is False
    assert config.LOGGING_LPP_FORMAT == "ShortFormat"
    config.validate()


def test_environment_overrides_every_family_of_field(reload_config: ReloadConfig) -> None:
    config = reload_config(
        DEV_MODE="true",
        SERVER_PORT="8123",
        MAX_BODY_BYTES="2048",
        LOCK_WAIT_TIMEOUT_SECONDS="12.5",
        DEVICE="cpu",
        NUM_THREADS="4",
        LOGGING_ENABLE_CONSOLE="false",
    )

    assert config.DEV_MODE is True
    assert config.SERVER_PORT == 8123
    assert config.MAX_BODY_BYTES == 2048
    assert config.LOCK_WAIT_TIMEOUT_SECONDS == 12.5
    assert config.DEVICE == "cpu"
    assert config.NUM_THREADS == 4
    assert config.LOGGING_ENABLE_CONSOLE is False


@pytest.mark.parametrize("value", ["false", "0", "no", ""])
def test_dev_mode_falsy_strings_are_off(reload_config: ReloadConfig, value: str) -> None:
    assert reload_config(DEV_MODE=value).DEV_MODE is False


def test_subclass_adds_a_field_and_redeclares_a_base_one() -> None:
    class PrefixedConfig(ServerConfig):
        EXTRA_KNOB: int = 7
        MAX_BODY_BYTES = 512

    assert PrefixedConfig.EXTRA_KNOB == 7
    assert PrefixedConfig.MAX_BODY_BYTES == 512
    assert PrefixedConfig.SERVER_PORT == ServerConfig.SERVER_PORT
    assert PrefixedConfig.to_dict()["EXTRA_KNOB"] == 7


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("SERVER_PORT", 0, "SERVER_PORT"),
        ("SERVER_PORT", 70_000, "SERVER_PORT"),
        ("MAX_BODY_BYTES", 0, "MAX_BODY_BYTES"),
        ("LOCK_WAIT_TIMEOUT_SECONDS", 0.0, "LOCK_WAIT_TIMEOUT_SECONDS"),
        ("GZIP_MINIMUM_SIZE", -1, "GZIP_MINIMUM_SIZE"),
        ("DEVICE", "tpu", "DEVICE"),
        ("NUM_THREADS", -2, "NUM_THREADS"),
    ],
)
def test_validate_rejects_out_of_range_values(field: str, value: object, message: str) -> None:
    broken: type[ServerConfig] = type("BrokenConfig", (ServerConfig,), {field: value})

    with pytest.raises(ValueError, match=message):
        broken.validate()
