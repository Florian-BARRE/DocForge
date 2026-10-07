# ---------------------- Key generation + hashing ---------------------- #
from .keys import AuthKeys

# ---------------------- Authenticated identity ---------------------- #
from .principal import AuthPrincipal

# ---------------------- AuthN dependency (the gate) ---------------------- #
from .dependency import authenticate, evict_cached_key

# ---------------------- AuthN ASGI middleware (pre-body gate) ---------------------- #
from .middleware import AuthMiddleware

# ---------------------- AuthZ vocabulary + gate ---------------------- #
from .capability import CANONICAL_CAPABILITIES, Capability
from .profiles import KeyProfile, KeyProfiles
from .permissions import KeyPermissions
from .authz import require, AuthzGuard
from .scope_aliases import KeyScopeAliases
from .grant_guard import KeyGrantGuard

# ---------------------- Startup root provisioning ---------------------- #
from .bootstrap import AuthBootstrap

# ------------------- Public API ------------------- #
__all__ = [
    "AuthKeys",
    "AuthPrincipal",
    "authenticate",
    "evict_cached_key",
    "AuthMiddleware",
    "Capability",
    "CANONICAL_CAPABILITIES",
    "KeyProfile",
    "KeyProfiles",
    "KeyPermissions",
    "require",
    "AuthzGuard",
    "KeyScopeAliases",
    "KeyGrantGuard",
    "AuthBootstrap",
]
