# ====== Code Summary ======
# EncodeFailureMapper — maps a classified query-embedder probe outcome onto an HONEST HTTP error
# (424 for a permanent config/auth fault, 503 for a transient one).

# ====== Third-Party Library Imports ======
from fastapi import HTTPException
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from shared_libs.pipelines.reachability import ProbeStatus


class EncodeFailureMapper:
    """Static mapping of a query-embedder failure onto its HTTP error."""

    logger = loggerplusplus.bind(identifier="EncodeFailureMapper")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("EncodeFailureMapper is a static-only class and cannot be instantiated.")

    @staticmethod
    def encode_failure_http(status: ProbeStatus, detail: str) -> HTTPException:
        """
        Map a classified query-embedder probe outcome onto an HONEST encode-failure HTTP error.

        The point is that a caller can tell "fix your config" from "retry shortly": a permanent
        config/auth fault is a 424 (Failed Dependency) naming WHAT is wrong, never a transient 503.

        Mapping:
            - ``unreachable``   → 424 ``embedder_unreachable`` (dead host / transport / drifted blob).
            - ``auth_failed``   → 424 ``embedder_auth_failed`` (the endpoint rejected the credentials).
            - anything else (``ok`` / ``not_configured`` / ``skipped``) → 503 ``embedder_overloaded``
              (the embedder answered the probe, so the original failure was genuinely transient).

        Args:
            status (ProbeStatus): The query-embedder probe outcome.
            detail (str): The human-readable reason (the original encode failure message).

        Returns:
            HTTPException: The status-coded, machine-readable error the route raises.
        """
        # 1. Permanent config faults are a Failed-Dependency 424 with a machine-readable code.
        if status == ProbeStatus.UNREACHABLE:
            return HTTPException(
                status_code=424,
                detail={"code": "embedder_unreachable", "detail": detail},
            )
        if status == ProbeStatus.AUTH_FAILED:
            return HTTPException(
                status_code=424,
                detail={"code": "embedder_auth_failed", "detail": detail},
            )
        # 2. The embedder answered the probe → the failure was transient; a retryable 503.
        return HTTPException(
            status_code=503,
            detail={"code": "embedder_overloaded", "detail": detail},
        )


__all__ = ["EncodeFailureMapper"]
