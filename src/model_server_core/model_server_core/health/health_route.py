# ====== Code Summary ======
# HealthRoute: GET /health, the liveness + readiness probe shared by every model host. HTTP 503 while
# the service is still building (status="loading") or when the host can never serve
# (status="unhealthy"), so compose healthchecks and the DocForge worker's preflight never hit an unready
# container. Logged at DEBUG only: health is polled at high frequency.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import Final

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Response
from loggerplusplus import LoggerClass

# ====== Local Project Imports ======
from .health_models import HealthResponse, HealthStatus
from .health_source import HealthSource

# ====== Constants ======
HEALTH_PATH: Final[str] = "/health"


class HealthRoute(LoggerClass):
    """Builds the router that serves GET /health.

    Args:
        source (HealthSource): Where readiness, blockers and the device come from.
        response_model (type[HealthResponse]): Documented body model (a subclass when the server
            reports more fields).
    """

    # Public attributes
    router: APIRouter

    # Private attributes
    _source: HealthSource

    def __init__(
        self, source: HealthSource, response_model: type[HealthResponse] = HealthResponse
    ) -> None:
        LoggerClass.__init__(self)
        self._source = source
        self.router = APIRouter()
        self.router.add_api_route(
            HEALTH_PATH, self.handle, methods=["GET"], response_model=response_model
        )

    # =======================
    #   Public Methods
    # =======================
    async def handle(self, response: Response) -> HealthResponse:
        """Liveness + readiness probe.

        Args:
            response (Response): FastAPI response object used to set the HTTP status code.

        Returns:
            HealthResponse: 200 "ok" when ready; 503 "unhealthy" or "loading" otherwise.
        """
        self.logger.debug("GET /health")

        # 1. Hard gate: a host that can never serve is reported up front, before readiness, so the
        #    container never advertises a readiness it cannot honour.
        blocker = self._source.health_blocker()
        if blocker is not None:
            response.status_code = 503
            return self._source.build_health(HealthStatus.UNHEALTHY, False, blocker)

        # 2. Readiness: the model service must be built before any request is served.
        if not self._source.is_ready():
            response.status_code = 503
            return self._source.build_health(HealthStatus.LOADING, False, "Model is still loading.")

        return self._source.build_health(HealthStatus.OK, True, None)
