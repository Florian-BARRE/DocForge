# ====== Code Summary ======
# SectionSplitter protocol + SplitPiece — the interchangeable "how to cut an oversize section"
# contract. The S4 orchestrator builds the heading skeleton and packs small sections; only when
# a section exceeds the token budget does it delegate to the configured splitter. Each splitter
# is selected by SplitMethodSpec.id and reads its own params (the decision-tree-by-method).

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# ====== Internal Project Imports ======
from libs.core.ir.models import Block


@dataclass(slots=True)
class SplitPiece:
    """
    One chunk-worth of content produced by a splitter from a single section.

    A piece may span whole blocks (token_budget / semantic) or a sub-block sentence window
    (sentence_window); ``block_ids`` always records every source block it touches, for
    provenance and for highlight-on-page.

    Attributes:
        text (str): The piece's rendered body text.
        block_ids (list[str]): Source block ids spanned by the piece (in reading order).
    """

    text: str
    block_ids: list[str] = field(default_factory=list)


@runtime_checkable
class SectionSplitter(Protocol):
    """
    Splits one section's content blocks into chunk-sized pieces.

    Implementations are interchangeable behind this Protocol (spec principle 2): the registry
    selects one from ``SplitMethodSpec.id`` and the orchestrator calls it for oversize sections.

    Attributes:
        name (str): Method id used in the config hash and the chunk ``strategy`` field.
    """

    name: str

    @property
    def max_tokens(self) -> int:
        """Token budget the orchestrator uses when packing small sibling sections."""
        ...

    def signature(self) -> dict[str, Any]:
        """Return the method id + resolved params for the deterministic S4 config hash."""
        ...

    async def split_section(self, blocks: list[Block]) -> list[SplitPiece]:
        """
        Split a section's content blocks into pieces no larger than the token budget.

        Args:
            blocks (list[Block]): The section's content blocks in reading order.

        Returns:
            list[SplitPiece]: Ordered pieces; one element when the section already fits.
        """
        ...
