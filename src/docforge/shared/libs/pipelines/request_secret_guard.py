# ====== Code Summary ======
# RequestSecretGuard — the write-side half of the endpoint rule for providers that take their endpoint
# from a REQUEST artefact instead of their own config. A structgen step inside a metagen ForEach calls
# the GenerationRequest's endpoint (resolved by the prep node: its default endpoint, or a per-field
# target's), and its own config is only an OVERRIDE. A step override pointed at an endpoint none of the
# prep's keys belong to, while OMITTING its own key, could only work by inheriting a request key — which
# the runtime never sends to a foreign endpoint (SecretIdentity.scoped_secret). Such a write is refused
# so the caller states the step's key explicitly (or ``""`` to call it keyless).

# ====== Standard Library Imports ======
from collections.abc import Iterator
from typing import Any

# ====== Internal Project Imports ======
from shared_libs.pipelines.nested_secrets import NestedSecrets
from shared_libs.pipelines.secret_identity import SecretIdentity

# The families whose steps inherit their endpoint (and key) from the request they process.
REQUEST_ENDPOINT_FAMILIES: frozenset[str] = frozenset({"structgen"})

# The secret a request endpoint carries (an OpenAICompatConfig has no other).
REQUEST_SECRET = "api_key"


class RequestSecretGuard:
    """Static detector of request-endpoint steps relying on a request key at a foreign endpoint."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("RequestSecretGuard is a static-only class and cannot be instantiated.")

    @classmethod
    def __nodes(cls, nodes: Any) -> Iterator[dict[str, Any]]:
        """Every node dict of a node list, recursing groups and ForEach bodies."""
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):
                continue
            yield node
            yield from cls.__nodes(node.get("nodes"))
            body = node.get("body")
            if isinstance(body, dict):
                yield from cls.__nodes(body.get("nodes"))

    @classmethod
    def __parent_endpoints(cls, parent: dict[str, Any]) -> set[str]:
        """The endpoints the ForEach's feeding node holds a live request key for."""
        config = parent.get("config")
        if not isinstance(config, dict):
            return set()
        endpoint = SecretIdentity.effective_endpoint(
            parent.get("family"), parent.get("kind"), config
        )
        return NestedSecrets.endpoints_with_secret(config, endpoint, REQUEST_SECRET)

    @classmethod
    def violations(cls, blob: dict[str, Any] | None) -> list[tuple[str, str]]:
        """
        The request-endpoint steps that omit their key at an endpoint no request key belongs to.

        Args:
            blob (dict | None): The (secret-healed) inbound pipeline blob.

        Returns:
            list[tuple[str, str]]: ``(node_id, "api_key")`` per offending step.
        """
        if not isinstance(blob, dict):
            return []
        nodes = list(cls.__nodes(blob.get("nodes")))
        by_id = {node.get("id"): node for node in nodes if isinstance(node.get("id"), str)}
        found: list[tuple[str, str]] = []
        for loop in nodes:
            over, body = loop.get("over"), loop.get("body")
            if not isinstance(over, dict) or not isinstance(body, dict):
                continue
            parent = by_id.get(over.get("node_id"))
            keyed = cls.__parent_endpoints(parent) if parent is not None else set()
            if not keyed:
                continue
            for step in cls.__nodes(body.get("nodes")):
                config = step.get("config")
                if step.get("family") not in REQUEST_ENDPOINT_FAMILIES or not isinstance(
                    config, dict
                ):
                    continue
                own = SecretIdentity.endpoint(config)
                if own is not None and own not in keyed and REQUEST_SECRET not in config:
                    found.append((str(step.get("id")), REQUEST_SECRET))
        return found


__all__ = ["REQUEST_ENDPOINT_FAMILIES", "REQUEST_SECRET", "RequestSecretGuard"]
