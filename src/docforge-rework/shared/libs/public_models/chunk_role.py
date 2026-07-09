# ====== Code Summary ======
# The structural classification of a chunk and the single canonical policy that maps it to a
# default enabled state. `role` is what the pipeline assigns (a structural label on the pure
# Chunk artefact); the user's mutable enable/disable override and the effective-state resolution
# live at the DB/read layer, never here — this module stays pure.

# ====== Standard Library Imports ======
from enum import StrEnum


class ChunkRole(StrEnum):
    """
    Structural classification of a chunk — what kind of content it carries.

    Assigned by the pipeline (a structural label, not a user choice). It drives the default
    enabled state via :func:`role_default_enabled`. The set is intentionally extensible; these
    are the initial members.
    """

    BODY = "body"                    # substantive content — the retrievable payload
    HEADER_FOOTER = "header_footer"  # running header/footer furniture — off by default
    TOC = "toc"                      # table of contents / index scaffolding — off by default
    BOILERPLATE = "boilerplate"      # repeated legal/notice/navigation text — off by default


def role_default_enabled(role: ChunkRole) -> bool:
    """
    Return the default enabled state for a chunk role.

    This is THE single place the role -> default-enabled mapping is defined; the embed filter,
    the worker, and search all import it. Only ``BODY`` defaults to enabled; every non-body role
    (header/footer, table of contents, boilerplate) defaults to disabled and is hidden from search
    unless the user overrides it.

    Args:
        role (ChunkRole): The structural role assigned to the chunk.

    Returns:
        bool: ``True`` if chunks of this role are searchable by default, ``False`` otherwise.
    """
    return role is ChunkRole.BODY


__all__ = ["ChunkRole", "role_default_enabled"]
