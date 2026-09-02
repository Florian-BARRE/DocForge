# ====== Code Summary ======
# AuditTargetParser — best-effort extraction of the (target_type, target_id) an audited request acts
# on, parsed from the CONCRETE request path (so the real resource UUID is captured, unlike the
# low-cardinality route template stored in the `path` column). It recognises the platform's main
# mutable resources — collections, documents, jobs, chunks and API keys — and only accepts
# the following path segment as the id when it parses as a real UUID. That single rule cleanly rejects
# sub-action words ("import", "reingest", "enabled", "rotate") and the bulk endpoints (no id), leaving
# target_id NULL there rather than storing a bogus value. Anything unrecognised yields (None, None).

# ====== Standard Library Imports ======
from __future__ import annotations

import uuid

# The /api/v1 prefix every audited path carries; stripped before segment parsing.
_API_PREFIX = "/api/v1"

# Leading path segment → the target type it denotes. `auth` is special-cased (its resource is the
# second segment, `keys`) in the parser below.
_RESOURCE_TYPES: dict[str, str] = {
    "collections": "collection",
    "documents": "document",
    "jobs": "job",
    "chunks": "chunk",
}


class AuditTargetParser:
    """Static helper mapping a concrete API path to the resource it acts on (best-effort)."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("AuditTargetParser is a static-only class and cannot be instantiated.")

    @staticmethod
    def parse(path: str) -> tuple[str | None, str | None]:
        """
        Extract the (target_type, target_id) a request path acts on.

        Args:
            path (str): The concrete request path (``scope["path"]``), e.g.
                ``/api/v1/collections/1f...e2/export``.

        Returns:
            tuple[str | None, str | None]: The recognised target type and its UUID id — either may
            be None (an unrecognised resource, or a resource with no id in the path such as a create
            or bulk action).
        """
        # 1. Only /api/v1 paths carry an auditable resource; strip the prefix and split.
        if not path.startswith(_API_PREFIX):
            return None, None
        segments = [segment for segment in path[len(_API_PREFIX) :].split("/") if segment]
        if not segments:
            return None, None

        # 2. API keys live under /auth/keys/{key_id}; resolve them before the flat resource map.
        if segments[0] == "auth" and len(segments) >= 2 and segments[1] == "keys":
            return "key", AuditTargetParser._uuid_or_none(segments, 2)

        # 3. A recognised leading resource keyword; its id (when present) is the next segment.
        target_type = _RESOURCE_TYPES.get(segments[0])
        if target_type is None:
            return None, None
        return target_type, AuditTargetParser._uuid_or_none(segments, 1)

    @staticmethod
    def _uuid_or_none(segments: list[str], index: int) -> str | None:
        """
        Return ``segments[index]`` only when it is present and parses as a UUID, else None.

        The UUID gate is what distinguishes a real resource id from a sub-action word (``import``,
        ``reingest``, ``enabled``, ``rotate``) or an absent id (a create / bulk endpoint).

        Args:
            segments (list[str]): The path segments (prefix already stripped).
            index (int): The segment position that would hold the id.

        Returns:
            str | None: The canonical id string when the segment is a UUID, else None.
        """
        # 1. No segment at that position → no id (a create or a top-level action).
        if index >= len(segments):
            return None
        # 2. Accept the segment only when it is a genuine UUID (rejects sub-action words).
        try:
            return str(uuid.UUID(segments[index]))
        except ValueError:
            return None


__all__ = ["AuditTargetParser"]
