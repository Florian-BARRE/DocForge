# ---------------------- Key generation + hashing ---------------------- #
from .keys import AuthKeys

# ---------------------- Authenticated identity ---------------------- #
from .principal import AuthPrincipal

# ---------------------- AuthN dependency (the gate) ---------------------- #
from .dependency import authenticate

# ---------------------- AuthN ASGI middleware (pre-body gate) ---------------------- #
from .middleware import AuthMiddleware

# ---------------------- AuthZ vocabulary + gate ---------------------- #
from .permissions import Capability, KeyPermissions
from .authz import require, AuthzGuard

# ---------------------- Startup root provisioning ---------------------- #
from .bootstrap import AuthBootstrap

# ------------------- Public API ------------------- #
__all__ = [
    "AuthKeys",
    "AuthPrincipal",
    "authenticate",
    "AuthMiddleware",
    "Capability",
    "KeyPermissions",
    "require",
    "AuthzGuard",
    "AuthBootstrap",
]
