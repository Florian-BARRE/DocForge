# ====== Code Summary ======
# BaseParserHelpers — parser-agnostic post-passes every parser's mapper can apply to its blocks.
# `assign_heading_tree` builds the heading hierarchy (block.parent_id) from the reading order and
# the heading levels: every block hangs under the nearest open heading, and a heading closes every
# heading of an equal or deeper level. This is what breadcrumbs (contextualize) and section-aware
# chunking walk later.

# ====== Internal Project Imports ======
from shared_libs.public_models import Block, BlockType


class BaseParserHelpers:
    """Static parser-agnostic post-passes over freshly mapped blocks — pure, no side effects."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("BaseParserHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def assign_heading_tree(blocks: list[Block]) -> None:
        """
        Fill every block's parent_id from the heading structure (in place).

        Args:
            blocks (list[Block]): The document's blocks, in reading order.
        """
        # Stack of currently open headings, shallowest first (levels strictly increasing).
        stack: list[Block] = []
        for block in blocks:
            if block.block_type == BlockType.HEADING:
                # 1. A heading closes every heading at its own level or deeper.
                level = block.level or 1
                while stack and (stack[-1].level or 1) >= level:
                    stack.pop()
                block.parent_id = stack[-1].id if stack else None
                stack.append(block)
            else:
                # 2. Any other block hangs under the nearest open heading.
                block.parent_id = stack[-1].id if stack else None


__all__ = ["BaseParserHelpers"]
