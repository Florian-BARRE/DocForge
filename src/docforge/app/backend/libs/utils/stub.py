# ====== Code Summary ======
# StubHelpers: static utility for scaffolded-but-unimplemented endpoints.
# Raises HTTP 501 with a uniform payload so the full API surface is browsable
# in Swagger while each endpoint is populated incrementally.

# ====== Third-Party Library Imports ======
from fastapi import HTTPException


class StubHelpers:
    """
    Static helpers for scaffolded (not-yet-implemented) route handlers.

    Raises HTTP 501 with a uniform payload so the full API surface stays
    browsable in OpenAPI/Swagger while endpoints are implemented incrementally.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError(f"{cls.__name__} is a static-only class and cannot be instantiated.")

    @staticmethod
    def not_implemented(capability: str, needs: str = "") -> None:
        """
        Raise a uniform HTTP 501 for a scaffolded endpoint.

        Args:
            capability (str): Human label of the endpoint/capability being stubbed.
            needs (str): Optional note on what is required to implement it.

        Raises:
            HTTPException: Always — HTTP 501 Not Implemented.
        """
        # 1. Build the detail payload (include 'needs' only when provided)
        detail: dict = {"status": "not_implemented", "capability": capability}
        if needs:
            detail["needs"] = needs

        # 2. Raise 501
        raise HTTPException(status_code=501, detail=detail)


# Module-level alias so existing callers import `not_implemented` directly.
not_implemented = StubHelpers.not_implemented

__all__ = ["StubHelpers", "not_implemented"]
