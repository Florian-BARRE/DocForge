# ====== Code Summary ======
# PlaceholderEndpointNotices — the edit-time endpoint caveats over an assembled blob. An ENABLED
# provider node still pointed at a template placeholder (unreachable host / SET_ME key), with an empty
# base_url, or a hosted https endpoint without an api_key builds fine (GraphValidator is structural
# only) but fails at the first spend or at preflight — so it is surfaced as a notice at edit time.

# ====== Standard Library Imports ======
from collections.abc import Iterator

# ====== Internal Project Imports ======
from shared_libs.pipelines.build.blob import GroupNodeBlob


class PlaceholderEndpointNotices:
    """Static scan of an assembled blob for enabled nodes with a placeholder or missing endpoint."""

    # The template's pre-filled but non-executable endpoints — a stage shipping OFF carries these
    # until the user opts in and sets a real one; enabled while still holding one is worth flagging.
    _PLACEHOLDER_MARKERS = ("vlm:8000", "llm:8000", "SET_ME")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "PlaceholderEndpointNotices is a static-only class and cannot be instantiated."
        )

    @classmethod
    def __endpoint_notice(cls, node_id: str, config: object) -> str | None:
        """The edit-time endpoint caveat for one enabled action node, or ``None`` when it is sound.

        The assembled blob holds only ENABLED stages' nodes, so every node reached here is live.
        A missing endpoint (or a template placeholder) builds cleanly — GraphValidator is structural
        only — and would otherwise fail at the first spend (or at preflight). Surfacing it here, at
        edit time, lets the user wire a real endpoint before ingesting rather than discovering it
        from a failed job.

        Args:
            node_id (str): The node whose config is inspected (named in the notice).
            config (object): The node's config dict (any non-dict is treated as endpoint-free).

        Returns:
            str | None: The caveat to surface, or ``None`` when the node needs none.
        """
        # 0. A fully-local classify backend needs no endpoint at all — never flag its empty base_url
        #    (it classifies offline via RapidOCR, so there is nothing to preflight).
        if isinstance(config, dict) and config.get("classify_backend") == "local":
            return None
        # 1. A template placeholder endpoint/key — a stage shipping OFF carries these until opt-in.
        if any(marker in repr(config) for marker in cls._PLACEHOLDER_MARKERS):
            return (
                f"node '{node_id}' still points at a template placeholder endpoint/key — set a "
                f"reachable URL and credentials before ingesting, or the run fails at preflight."
            )
        if not isinstance(config, dict):
            return None
        # 2. A network node with no endpoint at all — an empty base_url is never legitimate (an
        #    in-stack service still has a concrete host), so flag it whatever the node kind.
        base_url = config.get("base_url")
        if isinstance(base_url, str) and not base_url.strip():
            return (
                f"node '{node_id}' has no endpoint set (base_url is empty) — set a reachable URL "
                f"before ingesting, or the run fails at preflight."
            )
        # 3. A HOSTED endpoint (https) with an empty api_key — an in-stack http service legitimately
        #    needs no key, so the key is only flagged when the endpoint is a remote https one.
        api_key = config.get("api_key")
        if (
            isinstance(base_url, str)
            and base_url.strip().lower().startswith("https://")
            and isinstance(api_key, str)
            and not api_key.strip()
        ):
            return (
                f"node '{node_id}' points at a hosted endpoint with no api_key — set the credential "
                f"before ingesting, or the run fails at preflight."
            )
        return None

    @classmethod
    def __action_configs(cls, blob: GroupNodeBlob) -> Iterator[tuple[str, object]]:
        """Every action node's (id, config) in the graph, recursing ForEach bodies + sub-groups."""
        for node in blob.nodes:
            body = getattr(node, "body", None)  # ForEach body
            if body is not None:
                yield from cls.__action_configs(body)
            nested = getattr(node, "nodes", None)  # a nested Group exposes children under .nodes
            if nested is not None:
                yield from cls.__action_configs(node)
            config = getattr(node, "config", None)
            if config is not None:
                yield node.id, config

    @classmethod
    def warn(cls, blob: GroupNodeBlob, notices: list[str]) -> None:
        """
        Append one notice per enabled action node with a placeholder or missing endpoint/key.

        Args:
            blob (GroupNodeBlob): The assembled blob (only enabled stages' nodes are present).
            notices (list[str]): Collector the caveats are appended to (one per node at most).
        """
        flagged: set[str] = set()
        for node_id, config in cls.__action_configs(blob):
            if node_id in flagged:
                continue
            notice = cls.__endpoint_notice(node_id, config)
            if notice is not None:
                flagged.add(node_id)
                notices.append(notice)


__all__ = ["PlaceholderEndpointNotices"]
