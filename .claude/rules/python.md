---
paths:
  - "**/*.py"
---

# Python Project Rules

> These rules extend the general code rules. Apply both together.

---

## Dependency Management — uv

All Python projects use **uv** as the package manager and dependency resolver.

- Dependencies are declared in `pyproject.toml` and locked in `uv.lock`.
- Add packages with `uv add <package>` — never use `pip install` directly.
- Custom libraries used across all projects: `loggerplusplus` (logging) and `configplusplus` (configuration).

---

## `loggerplusplus` — Logging

Custom logging library (wrapper around loguru).

**Never use `print()` or loguru directly.** All logging goes exclusively through `loggerplusplus`.

### Setup — sinks

Always call `loggerplusplus.remove()` first to clear default sinks, then add your own:

```python
from loggerplusplus import loggerplusplus
from loggerplusplus import formats as lpp_formats
import sys, pathlib

loggerplusplus.remove()  # Always called first

loggerplusplus.add(
    sink=sys.stdout,
    level="DEBUG",
    format=lpp_formats.ShortFormat(),   # or DebugFormat(), or a custom format string
)

# File sink with rotation
loggerplusplus.add(
    pathlib.Path("logs"),
    level="INFO",
    format=lpp_formats.DebugFormat(),
    rotation="1 week",
    retention="30 days",
    compression="zip",
    encoding="utf-8",
    enqueue=True,
    backtrace=True,
    diagnose=False,
)
```

Available built-in formats (from `loggerplusplus.formats`): `ShortFormat`, `DebugFormat`.

### Usage in classes

**Instanciable class → inherit `LoggerClass`, call its `__init__`, use `self.logger`:**

```python
from loggerplusplus import LoggerClass

class MyService(LoggerClass):
    def __init__(self) -> None:
        LoggerClass.__init__(self)   # Required — initializes self.logger
        self.logger.info(f"MyService initialized")
```

**Static-only class → bind a module-level logger with `loggerplusplus.bind()`:**

```python
from loggerplusplus import loggerplusplus

class MyHelpers:
    logger = loggerplusplus.bind(identifier="MyHelpers")

    @classmethod
    def do_something(cls) -> None:
        cls.logger.debug(f"Processing something")
```

### Log levels

- `logger.debug(...)` — internal state, intermediate values, tracing
- `logger.info(...)` — key lifecycle events (init, start, stop, completion)
- `logger.warning(...)` — recoverable issues, unexpected but non-fatal situations
- `logger.error(...)` — failures, caught exceptions with context
- `logger.exception(...)` — unexpected exceptions (includes full traceback automatically)

**All log messages must be f-strings**, even static ones:
```python
self.logger.info(f"Service started")   # Correct
self.logger.info("Service started")    # Wrong
```

> **Note:** this convention triggers ruff rule `F541` (f-string without placeholder).
> Add `"F541"` to `[lint.ignore]` in `pyproject.toml` for all projects.

### Useful decorators

```python
from loggerplusplus import catch, log_timing, log_io

# Auto-catch and log exceptions
@catch(identifier="WORKER", level="ERROR")
def risky_operation():
    ...

# Log execution time
@log_timing(identifier="TASK", enter_message="Starting {func}...", exit_message="Done in {duration:.2f}s")
def slow_operation():
    ...

# Log function arguments and/or return value
@log_io(identifier="CALC", log_args=True, log_return=True)
def compute(a: int, b: int) -> int:
    return a + b
```

---

## `configplusplus` — Configuration

Custom configuration library.

Two loaders depending on the source: `EnvConfigLoader` for environment variables, `YamlConfigLoader` for YAML files.

### `EnvConfigLoader` — environment variables

Used for `RUNTIME_CONFIG`. The class body is evaluated at import time — all `env()` calls read from the environment immediately.

```python
from configplusplus import EnvConfigLoader, env
import pathlib

class RUNTIME_CONFIG(EnvConfigLoader):
    # String (default)
    APP_NAME = env("APP_NAME")

    # With type casting
    PORT = env("PORT", cast=int)
    DEBUG = env("DEBUG", cast=bool)
    TIMEOUT = env("TIMEOUT", cast=float)
    DATA_DIR = env("DATA_DIR", cast=pathlib.Path)

    # With default value (won't raise if missing)
    LOG_LEVEL = env("LOG_LEVEL", default="INFO")

    # Optional (returns None if missing)
    OPTIONAL_KEY = env("OPTIONAL_KEY", required=False, default=None)
```

Boolean casting rules — these strings evaluate to `False`: `"false"`, `"False"`, `"FALSE"`, `"0"`, `"no"`, `"No"`, `"NO"`, `""`. All other non-empty strings are `True`.

**Secret masking** — variables whose name contains `SECRET`, `API_KEY`, `PASSWORD`, `TOKEN`, or `CREDENTIAL` are automatically masked when the config is printed. Useful for debug logging of the full config at startup.

**Loading `.env` files:**
```python
from configplusplus import safe_load_envs

safe_load_envs()                    # Loads all *.env files in current directory
safe_load_envs(".env.production")   # Loads a specific file
safe_load_envs(verbose=False)       # Silent mode
```

If the project runs in a container with env vars injected directly (Docker, K8s), `safe_load_envs` is not needed.

**Custom validation:**
```python
class RUNTIME_CONFIG(EnvConfigLoader):
    PORT = env("PORT", cast=int)

    @classmethod
    def validate(cls) -> None:
        super().validate()
        if cls.PORT < 1024:
            raise RuntimeError("PORT must be >= 1024")
```

### `YamlConfigLoader` — YAML files

Used for application-specific configs (scrapers, pipelines, etc.) that don't belong in `.env`.

```python
from configplusplus import YamlConfigLoader

class BaseScraperConfigLoader(YamlConfigLoader):
    def __post_init__(self) -> None:
        cfg = self._raw_config  # Raw parsed YAML dict

        self.name: str = cfg["name"]
        self.base_url: str = cfg["base_url"]
        self.timeout: float = float(cfg["timeout"])

        # Nested structures
        self.headers: dict[str, str] = dict(cfg.get("headers", {}))
```

Helper methods available on any `YamlConfigLoader` instance:
```python
config = MyConfig("config.yaml")

config.get("database.host")               # Dot notation access
config.get("api.timeout", default=30)     # With default
config.has("database.host")               # Returns bool
config.to_dict()                          # Full config as dict
```

Instantiate YAML configs in the `__init__.py` of the config group using paths from `RUNTIME_CONFIG`:
```python
# config/scraper_config/__init__.py
from ..runtime import RUNTIME_CONFIG
from .yahoo_config import YahooConfigLoader

YAHOO_CONFIG = YahooConfigLoader(config_path=RUNTIME_CONFIG.YAML_CONFIG_YAHOO_PATH)
```

---

## Project Structure

Every Python project must follow this layout:

```
project_root/
├── config/                    # Always named 'config', never 'config_loader'
│   ├── __init__.py            # Exposes RUNTIME_CONFIG + all instantiated configs
│   ├── runtime/
│   │   ├── __init__.py
│   │   └── runtime_config.py
│   └── <yaml_group>/          # Only if YAML configs exist (e.g. scraper_config/)
│       ├── __init__.py        # Instantiates all YAML configs from RUNTIME_CONFIG paths
│       ├── base_<n>.py
│       └── <provider>_config.py
├── libs/                      # All project sub-modules live here
│   └── <module>/
│       ├── __init__.py
│       ├── core.py
│       ├── params.py
│       ├── helpers.py
│       └── <sub_module>/
└── main.py                    # Entry point (or entrypoint.py for FastAPI — see fastapi.md)
```

**Exception — single runtime config, no YAML:** use a flat `config_loader.py` file at the project root instead of a `/config` folder.

> **Note:** when combined with Docker, this entire tree lives inside `src/<app_name>/`.
> See docker.md for the full combined layout.

---

## Configuration System

### `RUNTIME_CONFIG` — Always Imported First

`RUNTIME_CONFIG` **must be imported before any other internal import** in every entry point. Its class body calls `sys.path.append()` to register `libs/` paths — if it's not imported first, all internal module imports will fail.

```python
# Correct entry point import order
from config import RUNTIME_CONFIG      # MUST be first — registers sys.path
from libs.my_service import MyService  # Can now be resolved
```

### `runtime_config.py` — Required Structure

```python
# ====== Code Summary ======
# Defines RUNTIME_CONFIG (env-based settings) and configures the loggerplusplus sinks.
# This file is always the first module imported in any entry point.

# ====== Standard Library Imports ======
import os
import pathlib
import sys

# ====== Third-Party Library Imports ======
from configplusplus import EnvConfigLoader, env
from loggerplusplus import loggerplusplus
from loggerplusplus import formats as lpp_formats

# ─── Reset logger before anything else ───
loggerplusplus.remove()

# ─── Optional DEV_MODE early logger ───
# DEV_MODE is read directly from os.environ (not via env()) because it must
# activate a temporary debug sink BEFORE the RUNTIME_CONFIG class is evaluated.
# This sink is removed immediately after and replaced by the real sinks below.
if os.environ.get("DEV_MODE"):
    loggerplusplus.add(sink=sys.stdout, level="DEBUG", format=lpp_formats.ShortFormat())
    dev_mode_logger = loggerplusplus.bind(identifier="DEV")
    dev_mode_logger.warning(f"DEV MODE is activated !")
    loggerplusplus.remove()


class RUNTIME_CONFIG(EnvConfigLoader):
    # ───── Paths & dirs ─────
    PATH_ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent.parent
    PATH_LIBS = PATH_ROOT_DIR / "libs"

    # Register internal libs — must be inside the class body
    sys.path.append(str(PATH_LIBS))

    # ───── Logging (ALWAYS present in every project) ─────
    LOGGING_CONSOLE_LEVEL = env("LOGGING_CONSOLE_LEVEL")
    LOGGING_FILE_LEVEL = env("LOGGING_FILE_LEVEL")
    LOGGING_ENABLE_CONSOLE = env("LOGGING_ENABLE_CONSOLE", cast=bool)
    LOGGING_ENABLE_FILE = env("LOGGING_ENABLE_FILE", cast=bool)
    LOGGING_LPP_FORMAT = env("LOGGING_LPP_FORMAT")

    # ───── Project-specific variables ─────
    # Add project-specific env vars below this line.


# ─── Apply logging configuration AFTER class definition ───
lpp_format = getattr(lpp_formats, RUNTIME_CONFIG.LOGGING_LPP_FORMAT, lpp_formats.DebugFormat())()

if RUNTIME_CONFIG.LOGGING_ENABLE_CONSOLE:
    loggerplusplus.add(
        sink=sys.stdout,
        level=RUNTIME_CONFIG.LOGGING_CONSOLE_LEVEL,
        format=lpp_format,
    )

if RUNTIME_CONFIG.LOGGING_ENABLE_FILE:
    loggerplusplus.add(
        pathlib.Path("logs"),
        level=RUNTIME_CONFIG.LOGGING_FILE_LEVEL,
        format=lpp_format,
        rotation="1 week",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )
```

Rules:
- `loggerplusplus.remove()` is always the first executable line of the file.
- The 5 `LOGGING_*` variables are **mandatory in every project** — they drive the logging setup.
- `sys.path.append()` calls go inside the class body, right after the path constants.

---

## OOP Patterns

### Instanciable Classes — `LoggerClass`

All instanciable classes must inherit `LoggerClass` and explicitly call its `__init__`:

```python
from loggerplusplus import LoggerClass

class MyService(LoggerClass):
    def __init__(self, name: str) -> None:
        LoggerClass.__init__(self)   # Required
        self._name = name
        self.logger.info(f"MyService '{name}' initialized")
```

### Static-Only Classes — Helpers

Helper classes with no instance state must block instantiation with `__new__`:

```python
from loggerplusplus import loggerplusplus

class MyHelpers:
    """Static utility helpers for MyService."""

    logger = loggerplusplus.bind(identifier="MyHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("MyHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    def parse_response(cls, payload: dict) -> dict | None:
        cls.logger.debug(f"Parsing payload with {len(payload)} keys")
        ...

    @staticmethod
    def build_params(symbol: str, key: str) -> dict[str, str]:
        return {"symbol": symbol, "apikey": key}
```

Rules:
- Always named `<ParentClass>Helpers` (e.g. `BaseDataScraperHelpers`, `DetectorHelpers`).
- Stored in a `helpers.py` file alongside the class it serves.
- `logger` is a class-level attribute bound with `loggerplusplus.bind(identifier="ClassName")`.
- Use `@classmethod` when the method uses `cls.logger`, `@staticmethod` otherwise.

### Abstract Base Classes with Generic Params

```python
from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from loggerplusplus import LoggerClass
from .params import BaseParams

ParamsType = TypeVar("ParamsType", bound=BaseParams)


class BaseService(ABC, LoggerClass, Generic[ParamsType]):
    def __init__(self, params: ParamsType) -> None:
        LoggerClass.__init__(self)
        self.params: ParamsType = params

    @abstractmethod
    async def execute(self) -> None: ...
```

Child classes bind the generic type explicitly:

```python
class ConcreteService(BaseService[ConcreteParams]):
    async def execute(self) -> None:
        self.logger.info(f"Executing '{self.params.name}'")
```

### Params — `@dataclass(slots=True)`

All parameter objects use `@dataclass(slots=True)`. Always include a `from_config` classmethod:

```python
from dataclasses import dataclass
from typing import Any
from .base_params import BaseParams

@dataclass(slots=True)
class ConcreteParams(BaseParams):
    extra_field: str

    @classmethod
    def from_config(cls, cfg: Any) -> "ConcreteParams":
        return cls(
            name=cfg.name,
            extra_field=cfg.extra_field,
        )
```

### Immutable Config Objects — `@dataclass(frozen=True)`

For configuration objects that must never be mutated after construction:

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class OverlayConfig:
    alpha_max: float = 0.60
    alpha_min: float = 0.05
```

---

## File Structure Rules

### File Header — `# ====== Code Summary ======`

Every non-trivial `.py` file (not `__init__.py`) opens with:

```python
# ====== Code Summary ======
# Brief description of this module's responsibility and what it provides.
```

### Import Order — Four Labeled Sections

```python
# ====== Standard Library Imports ======
import os
from abc import ABC, abstractmethod

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from pydantic import BaseModel

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG          # absolute imports from project root
from libs.db import DatabaseClient

# ====== Local Project Imports ======
from .params import MyParams               # relative imports within the same package
from .helpers import MyHelpers
```

### Class Method Order

Within a class, methods must appear in this order:
1. `__dunder__` methods (`__init__`, `__new__`, `__repr__`, etc.)
2. `__private` methods (double underscore prefix — name-mangled)
3. `_protected` methods (single underscore prefix)
4. `public` methods (no prefix)

### `__init__.py` — Sections and `__all__`

`__init__.py` files contain only imports, organized in labeled sections, always ending with `__all__`. Never include a `# ====== Code Summary ======` block.

```python
# ---------------------- Base ---------------------- #
from .base import BaseService

# ------------------- Providers ------------------- #
from .yahoo import YahooService
from .twelve_data import TwelveDataService

# ------------------- Public API ------------------- #
__all__ = [
    "BaseService",
    "YahooService",
    "TwelveDataService",
]
```

---

## `libs/` Sub-Module Layout

```
libs/
└── my_feature/
    ├── __init__.py       # Public API exports only
    ├── core.py           # Main class (or scraper.py, service.py…)
    ├── params.py         # Params dataclass
    ├── helpers.py        # Static-only helpers class
    └── sub_feature/      # Only if the sub-feature is non-trivial
        ├── __init__.py
        ├── core.py
        └── models.py
```

- When 2+ classes share logic, extract a `base/` sub-module with the abstract base and shared helpers.
- `helpers.py` always contains exactly one static-only `XxxHelpers` class. Split into `helpers_<topic>.py` if needed.

---

## General Python Rules

- Use `|` union syntax (`str | None`) over `Optional[str]` (Python 3.10+).
- Use `from __future__ import annotations` for files with forward references.
- Use `StrEnum` for string enumerations (Python 3.11+).
- Always read values from `RUNTIME_CONFIG` — never from `os.environ` in application code (the sole exception is the `DEV_MODE` early logger in `runtime_config.py`).
