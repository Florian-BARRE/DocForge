# model_server_core

The shared core of the DocForge model-host micro-services (`bge_server`, `paddle_server`,
`mineru_server`, `dots_ocr_server`). It holds what the four servers used to duplicate: configuration
base, lifespan, `GET /health`, error handling, request guards, device probes and the entrypoint glue.

It is **model-free**: its only dependencies are `fastapi`, `uvicorn`, `pydantic`, `configplusplus` and
`loggerplusplus`. Nothing here imports torch, paddle or transformers; whatever needs them is injected
by the server that owns the heavy dependency.

> Status: the library exists and is tested, but **no server uses it yet** — each server adopts it in
> its own step.

## The bricks

| Class | Role |
|---|---|
| `ServerConfig` | configplusplus static config base: `DEV_MODE`, logging, host/port, `MAX_BODY_BYTES`, lock timeout, gzip, `DEVICE`, `NUM_THREADS`. Read once, injected as the class. |
| `LoggingBootstrap` | Applies the `LOGGING_*` / `DEV_MODE` section of a `ServerConfig` to the loggerplusplus sinks. |
| `ModelServer` | Abstract facade: builds the FastAPI app (lifespan, gzip, error handler, `/health`, your routes). |
| `ServerEntrypoint` | Thin glue for `entrypoint.py`: logging bootstrap, `app`, `run()`. |
| `ModelService` | Contract of the hosted model: `ready`, `load()`, `unload()`. |
| `ServerErrorHandler` | Unexpected exception → typed JSON 500 `{"detail": {"error", "correlation_id"}}`, never `str(exc)`; the full exception is logged with the same `correlation_id`. `InvalidInputError` → 422. |
| `RequestBodyGuard` | Reads a raw body under `MAX_BODY_BYTES` (413), `read_non_empty` adds the 422 on an empty body. |
| `InputValidator` | Pre-model body checks (non-empty, in-cap, decodable) with one `MediaDecoder` per `MediaKind`; `ImageDecoder` / `PdfDecoder` import Pillow / pypdfium2 lazily (the server depends on them, not the core). |
| `DeviceProbe` | `cuda` / `cpu`, memoized, from an injected chain of `CudaDetector`s (`NvidiaDriverDetector` ships, torch-free). |
| `CpuFeatureProbe` | `/proc/cpuinfo` flag probe (`supports("avx")`), assumes supported when it cannot prove absence. |
| `CpuBudget` | Effective CPU count honouring a cgroup v2 quota. |
| `HealthResponse` / `HealthStatus` / `HealthRoute` | The shared `/health` body and route. |

## Plugging a new server in

```python
# config_loader.py
class MyServerConfig(ServerConfig):
    MAX_BODY_BYTES = env(
        "MY_MAX_BODY_BYTES", cast=int, default="104857600"
    )  # keep a historical name
    MY_MODEL_PATH: str = env("MY_MODEL_PATH", default="/models/my")


# backend/my_server.py
class MyServer(ModelServer[MyServerConfig]):
    @property
    def title(self) -> str:  # abstract
        return "My model service"

    def model_service(self) -> ModelService:  # abstract
        return self._service

    def build_routes(self, app: FastAPI) -> None:  # abstract
        app.include_router(my_router(self.body_guard, self.input_validator, self._service))


# entrypoint.py  (zero logic)
entrypoint = ServerEntrypoint(MyServer(MyServerConfig))
app = entrypoint.app  # uvicorn entrypoint:app

if __name__ == "__main__":
    entrypoint.run()
```

Optional hooks on `ModelServer`: `version`, `startup()`, `shutdown()`, `health_blocker()` (a reason the
host can never serve — a missing CPU flag, no GPU), `build_health()` + `health_response_model` (extra
fields in `/health`), `configure_middlewares()`. Injectable through the constructor: `device_probe`,
`error_handler`, `input_validator`.

## Run the checks

```bash
uv sync --directory src/model_server_core
uv run --frozen --directory src/model_server_core pytest -q
uv run --frozen --directory src/model_server_core mypy --strict model_server_core
# the tests too (strict typing over the package and its tests)
MYPYPATH=tests uv run --frozen --directory src/model_server_core mypy --strict --explicit-package-bases model_server_core tests
uv run --frozen --directory src/model_server_core ruff check .
```
