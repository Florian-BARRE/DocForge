# ====== Code Summary ======
# TrivialModelServer: the smallest concrete ModelServer (a 5th server in miniature): a ServerConfig
# subclass with one extra field, a fake model service, and four routes exercising the shared bricks
# (the body guard, the input validator, an unexpected exception, an InvalidInputError).

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Any

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, FastAPI

# ====== Internal Project Imports ======
from model_server_core import (
    HealthResponse,
    HealthStatus,
    InvalidInputError,
    MediaKind,
    ModelServer,
    ModelService,
    ServerConfig,
)
from support.fakes.fake_model_service import FakeModelService


class TrivialServerConfig(ServerConfig):
    """ServerConfig subclass adding one server-specific field and a tiny body cap."""

    MODEL_NAME: str = "trivial"
    MAX_BODY_BYTES = 16


class TrivialHealthResponse(HealthResponse):
    """A richer /health body, the way bge reports its model ids."""

    model_name: str


class TrivialModelServer(ModelServer[TrivialServerConfig]):
    """Concrete server used by the suite; the hooks it overrides are switchable per instance."""

    health_response_model = TrivialHealthResponse

    def __init__(
        self,
        service: FakeModelService | None = None,
        *,
        blocker: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(TrivialServerConfig, **kwargs)
        self.service = service or FakeModelService()
        self.blocker = blocker
        self.events: list[str] = []

    @property
    def title(self) -> str:
        return "Trivial model server"

    @property
    def version(self) -> str:
        return "9.9.9"

    def model_service(self) -> ModelService:
        return self.service

    def health_blocker(self) -> str | None:
        return self.blocker

    def build_health(
        self, status: HealthStatus, ready: bool, detail: str | None
    ) -> TrivialHealthResponse:
        return TrivialHealthResponse(
            status=status.value,
            ready=ready,
            detail=detail,
            device=self.current_device(),
            model_name=TrivialServerConfig.MODEL_NAME,
        )

    def startup(self) -> None:
        self.events.append("startup")
        super().startup()

    def shutdown(self) -> None:
        self.events.append("shutdown")
        super().shutdown()

    def build_routes(self, app: FastAPI) -> None:
        router = APIRouter()

        @router.post("/echo")
        async def echo(body: bytes = Depends(self.body_guard.read_non_empty)) -> dict[str, int]:
            return {"size": len(body)}

        @router.post("/check-pdf")
        async def check_pdf(body: bytes = Depends(self.body_guard.read_capped)) -> dict[str, bool]:
            self.input_validator.validate(MediaKind.PDF, body)
            return {"valid": True}

        @router.get("/boom")
        async def boom() -> None:
            raise RuntimeError("secret internal detail: /srv/models/weights.bin")

        @router.get("/invalid")
        async def invalid() -> None:
            raise InvalidInputError("request body is not a decodable PDF")

        app.include_router(router)
