# ====== Code Summary ======
# ContextualizeHelpers — the pure embed_text builder, ported byte-for-byte from the v1 contextualize
# step. It assembles each chunk's embed_text as [doc title] + section breadcrumb + chunk body. The
# breadcrumb is precomputed by the chunk stage (chunk.prov["heading_path"]) so the section title appears
# exactly once and is never repeated in the body; the body is the chunk's raw_text. Static-only to keep
# the node body lean.

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from common_libs.domain import Chunk

# ====== Local Project Imports ======
from ..config import ContextualizeConfig


class ContextualizeHelpers:
    """Static helpers for the contextualize node — pure embed_text assembly."""

    logger = loggerplusplus.bind(identifier="ContextualizeHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("ContextualizeHelpers is a static-only class and cannot be instantiated.")

    @classmethod
    def build_embed_text(cls, chunk: Chunk, doc_title: str, cfg: ContextualizeConfig) -> str:
        """
        Build embed_text = [doc title] + section breadcrumb + chunk body.

        The breadcrumb comes precomputed from the chunk stage (``chunk.prov["heading_path"]``) — the
        section title therefore appears exactly once, in the breadcrumb, and is never repeated in the
        body. The body is the chunk's ``raw_text``, already assembled per chunk kind.

        Args:
            chunk (Chunk): Chunk whose embed_text is to be assembled.
            doc_title (str): Document title from the IR metadata (already stripped).
            cfg (ContextualizeConfig): Header-template controls (toggles + separators).

        Returns:
            str: The assembled embed_text string.
        """
        # 1. Section breadcrumb (precomputed) — only used when include_breadcrumb=True.
        breadcrumb = ""
        if cfg.include_breadcrumb and isinstance(chunk.prov, dict):
            breadcrumb = str(chunk.prov.get("heading_path", "")).strip()

        # 2. Prepend the doc title only when enabled AND not already the breadcrumb's first segment.
        prefix_parts: list[str] = []
        first_crumb = breadcrumb.split(cfg.breadcrumb_separator, 1)[0] if breadcrumb else ""
        if cfg.include_doc_title and doc_title and doc_title != first_crumb:
            prefix_parts.append(doc_title)
        if breadcrumb:
            prefix_parts.append(breadcrumb)

        # 3. Assemble — context header on one line, body separated per config.
        header = cfg.breadcrumb_separator.join(prefix_parts) if prefix_parts else ""
        parts = [p for p in [header, chunk.raw_text] if p.strip()]
        return cfg.header_body_separator.join(parts)


__all__ = ["ContextualizeHelpers"]
