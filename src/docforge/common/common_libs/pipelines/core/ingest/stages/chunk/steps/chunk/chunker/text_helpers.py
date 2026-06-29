# ====== Code Summary ======
# Shared, pure helpers for structure-aware chunking — token estimation, block->text rendering,
# sentence segmentation, heading-path utilities, provenance builders, and deterministic chunk
# UUIDs. No I/O; reused by the chunker engine and every section splitter so they stay consistent.

# ====== Standard Library Imports ======
import re
import uuid

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import Block, BlockType

# Characters-per-token heuristic shared across the platform (no tokenizer dependency).
_CHARS_PER_TOKEN: int = 4

# Sentence boundary: end punctuation (Latin + common CJK) followed by whitespace, or a newline.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+|\n+")

# Markdown image references produced by some OCR providers (e.g. Mistral) as noise artifacts.
# Pattern: ![alt text](url/path) — these are meaningless relative paths in OCR output.
_MD_IMAGE_RE = re.compile(r"!\[.*?\]\(.*?\)", re.DOTALL)


class ChunkingHelpers:
    """
    Static-only helpers shared by the chunker engine and the section splitters.

    Groups the pure text/provenance utilities so splitters render blocks, estimate tokens, and
    derive chunk identities identically — no behaviour drift between split methods.
    """

    logger = loggerplusplus.bind(identifier="ChunkingHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ChunkingHelpers is a static-only class and cannot be instantiated.")

    # --- Token estimation -----------------------------------------------------

    @classmethod
    def estimate_tokens_text(cls, text: str) -> int:
        """Estimate the token count of a raw string via the chars/4 heuristic."""
        return max(1, len(text) // _CHARS_PER_TOKEN)

    @classmethod
    def estimate_tokens(cls, block: Block) -> int:
        """
        Estimate a block's token count from its richest text projection.

        Args:
            block (Block): IR block (text / table / figure-enriched).

        Returns:
            int: Estimated token count (>= 1).
        """
        text = block.text or ""
        # 1. Tables / figures carry their text in structured fields, not block.text
        if block.table:
            text = " ".join(cell for row in block.table.cells for cell in row)
        elif block.figure:
            parts = filter(None, [
                block.figure.ocr_text,
                block.figure.description,
                " ".join(" ".join(row) for row in (block.figure.data_table or [])) or None,
            ])
            text = " ".join(parts)
        return max(1, len(text) // _CHARS_PER_TOKEN)

    # --- Text rendering -------------------------------------------------------

    @classmethod
    def block_to_text(cls, block: Block) -> str:
        """Render a single content block to plain text (no section heading)."""
        if block.type == BlockType.LIST_ITEM:
            return f"- {block.text or ''}"
        if block.type == BlockType.CODE:
            return f"```\n{block.text or ''}\n```"
        if block.type == BlockType.HEADING:
            # Defensive: a heading reaching the body renderer is shown inline
            return f"{'#' * (block.level or 1)} {block.text or ''}"
        if block.type == BlockType.TABLE:
            return cls.table_to_text(block)
        if block.type == BlockType.FIGURE:
            return cls.figure_to_text(block)
        # PARAGRAPH, CAPTION, FORMULA, and anything else -> raw text
        return block.text or ""

    @classmethod
    def table_to_text(cls, block: Block) -> str:
        """Render a TABLE block as pipe-separated rows (empty when no table data)."""
        if block.table is None:
            return ""
        return "\n".join(" | ".join(cell for cell in row) for row in block.table.cells)

    @classmethod
    def figure_to_text(cls, block: Block) -> str:
        """Render a FIGURE block as an [IMAGE] placeholder with OCR text + VLM description."""
        if block.figure is None:
            return ""
        # [IMAGE] marker lets retrieval/readers know visual content is present
        parts: list[str] = ["[IMAGE]"]
        if block.figure.ocr_text:
            # Strip markdown image refs injected by OCR providers (e.g. "![img.jpeg](img.jpeg)")
            clean = _MD_IMAGE_RE.sub("", block.figure.ocr_text).strip()
            if clean:
                parts.append(clean)
        if block.figure.description:
            parts.append(block.figure.description)
        if block.figure.data_table:
            parts.append("\n".join("\t".join(cell for cell in row) for row in block.figure.data_table))
        return "\n\n".join(p for p in parts if p.strip())

    @classmethod
    def blocks_to_text(cls, blocks: list[Block]) -> str:
        """Render content blocks into a single plain-text body (blank-line separated)."""
        parts = [cls.block_to_text(b) for b in blocks]
        return "\n\n".join(p for p in parts if p.strip())

    @classmethod
    def split_sentences(cls, text: str) -> list[str]:
        """
        Split text into sentences for window/semantic splitting.

        Args:
            text (str): Raw text.

        Returns:
            list[str]: Non-empty, stripped sentences in order.
        """
        if not text:
            return []
        return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]

    # --- Heading-path utilities -----------------------------------------------

    @classmethod
    def longest_common_prefix(cls, paths: list[list[str]]) -> list[str]:
        """Return the longest common leading sub-path shared by every path."""
        if not paths:
            return []
        common = paths[0]
        for p in paths[1:]:
            i = 0
            while i < len(common) and i < len(p) and common[i] == p[i]:
                i += 1
            common = common[:i]
            if not common:
                break
        return list(common)

    # --- Provenance builders --------------------------------------------------

    @classmethod
    def block_prov(cls, block: Block, heading_path: str) -> dict:
        """Build a provenance dict for a single block, tagged with its section breadcrumb."""
        return {
            "pages": [block.prov.page],
            "block_count": 1,
            "block_types": [block.type.value],
            "heading_path": heading_path,
        }

    @classmethod
    def aggregate_prov(cls, blocks: list[Block], heading_path: str) -> dict:
        """Aggregate provenance across blocks, tagged with the chunk's section breadcrumb."""
        return {
            "pages": sorted(set(b.prov.page for b in blocks)),
            "block_count": len(blocks),
            "block_types": sorted(set(b.type.value for b in blocks)),
            "heading_path": heading_path,
        }

    # --- Identity -------------------------------------------------------------

    @classmethod
    def stable_chunk_uuid(
        cls, doc_id: str, block_ids: list[str], config_hash: str, ordinal: int
    ) -> str:
        """
        Derive a stable chunk UUID from its content identity + position.

        The ordinal disambiguates chunks that share block ids (overlapping windows,
        sub-block semantic splits) while keeping ids deterministic across re-runs.

        Args:
            doc_id (str): Owning document id.
            block_ids (list[str]): Source block ids spanned by the chunk.
            config_hash (str): The chunking configuration hash.
            ordinal (int): Deterministic emission index used as a tie-breaker.

        Returns:
            str: A UUID5 string, stable for identical inputs.
        """
        identity = f"{doc_id}:{'|'.join(block_ids)}:{config_hash}:{ordinal}"
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, identity))


__all__ = ["ChunkingHelpers"]
