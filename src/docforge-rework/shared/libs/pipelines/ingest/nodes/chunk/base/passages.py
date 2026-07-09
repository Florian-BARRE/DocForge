# ====== Code Summary ======
# The COMMON projection every chunking method starts from: the enriched IR flattened into an
# ordered list of Passages. The composition RULES live here — once, for all methods: a figure and
# its meaning (the ADJACENT CAPTION block, folded in + VLM description + OCR text) become ONE
# ATOMIC unit that no method may split, rendered as an explicitly MARKED block so machine-derived
# text never reads as document prose; a table renders to markdown (atomic, caption folded in
# too); headings carry the section identity; decorative or empty figures contribute nothing.
# Header/footer furniture and table-of-contents scaffolding are NOT dropped: each passage carries
# a structural `role` (body by default) so downstream can keep them as disabled chunks. Every text
# is token-counted, and a boundary-less oversized text hard-cuts at token level — nothing
# non-atomic may exceed a method's cap.

# ====== Third-Party Library Imports ======
from pydantic import BaseModel, Field

# ====== Internal Project Imports ======
from shared_libs.public_models import Block, BlockType, ChunkRole, DocumentIR

# ====== Local Project Imports ======
from .config import BaseChunkerConfig
from .helpers import ChunkerHelpers

# Conservative, extensible allow-list of section titles that mark a table-of-contents section.
# Matched on the FULL normalized heading text (exact, never substring) so a real section like
# "Table of contributions" cannot be misread as scaffolding. Multilingual by design (the corpus
# is): add a title here when a language's ToC heading is confirmed. There is deliberately NO
# boilerplate allow-list — no reliable IR signal exists yet, so BOILERPLATE stays reserved.
_TOC_TITLES = frozenset(
    {
        "contents",
        "table of contents",
        "toc",
        "sommaire",
        "table des matières",
        "índice",
    }
)


class Passage(BaseModel):
    """
    One projected text unit — what every chunking method packs, cuts and regroups.

    Attributes:
        text (str): The unit's textual contribution.
        block_ids (list[str]): The IR blocks behind it (a fused caption adds its block here).
        heading_path (list[str]): Section ancestry TEXTS, top-down.
        section_key (list[str]): Section ancestry heading IDS — the section identity boundaries
            compare on (texts may collide, ids cannot).
        atomic (bool): True when no method may split this unit (figure+meaning, table).
        token_count (int): Token count of ``text``.
        role (ChunkRole): Structural classification of this unit (body / header-footer / toc);
            body by default. Furniture (non-body) passages are kept as disabled chunks, never
            mixed into a body chunk.
        page_start (int): First source page.
        page_end (int): Last source page.
    """

    text: str
    block_ids: list[str] = Field(default_factory=list)
    heading_path: list[str] = Field(default_factory=list)
    section_key: list[str] = Field(default_factory=list)
    atomic: bool = False
    token_count: int = 0
    role: ChunkRole = ChunkRole.BODY
    page_start: int = 0
    page_end: int = 0

    def explode(self, max_tokens: int, encoding_name: str) -> list["Passage"]:
        """
        Split this passage into sentence-level sub-passages when it exceeds a size bound.

        Args:
            max_tokens (int): Size above which a NON-ATOMIC passage must be cut; 0 means
                "always cut down to sentences" (no hard token bound).
            encoding_name (str): tiktoken encoding for the sub-counts.

        Returns:
            list[Passage]: Itself when atomic or within bounds; sentence sub-passages (sharing
            its blocks and section) otherwise. When a bound is set, a boundary-less sentence
            (run-on text, URL dump) is HARD-CUT at token level — the cap is a real invariant.
        """
        # 1. Atomic units and passages within bounds pass through untouched.
        if self.atomic or self.token_count <= max_tokens:
            return [self]
        # 2. Sentence pieces; any piece still above a real bound hard-cuts at token level.
        pieces: list[str] = []
        for sentence in ChunkerHelpers.split_sentences(self.text):
            if max_tokens > 0:
                pieces.extend(ChunkerHelpers.hard_split(sentence, max_tokens, encoding_name))
            else:
                pieces.append(sentence)
        return [
            self.model_copy(
                update={
                    "text": piece,
                    "token_count": ChunkerHelpers.count_tokens(piece, encoding_name),
                }
            )
            for piece in pieces
        ]


class PassageProjector:
    """Static projection of an enriched DocumentIR into the ordered Passage list."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("PassageProjector is a static-only class and cannot be instantiated.")

    @staticmethod
    def __ancestry(block: Block, by_id: dict[str, Block]) -> tuple[list[str], list[str]]:
        """Walk the heading tree up from a block → (heading texts, heading ids), top-down."""
        # 1. A heading belongs to ITS OWN section — start the walk at itself.
        texts: list[str] = []
        ids: list[str] = []
        seen: set[str] = set()
        cursor: Block | None = block if block.block_type == BlockType.HEADING else None
        if cursor is None and block.parent_id is not None:
            cursor = by_id.get(block.parent_id)
        # 2. The seen-guard protects against a CYCLIC parent chain — a corrupt IR from a non-tree
        #    source would otherwise hang this walk (and the worker) forever.
        while cursor is not None and cursor.id not in seen:
            seen.add(cursor.id)
            texts.append(cursor.text or "")
            ids.append(cursor.id)
            cursor = by_id.get(cursor.parent_id) if cursor.parent_id else None
        texts.reverse()
        ids.reverse()
        return texts, ids

    @staticmethod
    def __attach_captions(blocks: list[Block]) -> dict[str, Block]:
        """
        Map each FIGURE/TABLE block id to its adjacent CAPTION block.

        Parsers (docling included) emit captions as SEPARATE CAPTION blocks; the composition
        rule wants the caption INSIDE its figure/table unit. Adjacency in reading order decides
        ownership: the unit right after the caption first, else the one right before.
        """
        attached: dict[str, Block] = {}
        for index, block in enumerate(blocks):
            if block.block_type != BlockType.CAPTION or not (block.text and block.text.strip()):
                continue
            for neighbor_index in (index + 1, index - 1):
                if not 0 <= neighbor_index < len(blocks):
                    continue
                neighbor = blocks[neighbor_index]
                if (
                    neighbor.block_type in (BlockType.FIGURE, BlockType.TABLE)
                    and neighbor.id not in attached
                ):
                    attached[neighbor.id] = block
                    break
        return attached

    @staticmethod
    def __role_for(block: Block, heading_path: list[str]) -> ChunkRole:
        """
        Classify a block's structural role from IR signals (conservative, best-effort).

        Header/footer is an explicit IR block type. A table-of-contents is inferred from the
        section a block lives under: any heading in its ancestry whose FULL normalized text is a
        known ToC title (exact match, never substring) marks the whole section — heading and its
        list-like body alike — as scaffolding. Everything else is body. Boilerplate has no
        reliable IR signal yet, so it is never assigned here (the role stays reserved).

        Args:
            block (Block): The IR block behind the passage.
            heading_path (list[str]): The block's heading ancestry TEXTS, top-down.

        Returns:
            ChunkRole: The structural role of the passage this block produces.
        """
        # 1. Header/footer furniture is labelled directly from the IR block type.
        if block.block_type == BlockType.HEADER_FOOTER:
            return ChunkRole.HEADER_FOOTER
        # 2. A ToC section is inferred from the ancestry — any heading matching a known ToC title.
        if any(heading.strip().lower() in _TOC_TITLES for heading in heading_path):
            return ChunkRole.TOC
        return ChunkRole.BODY

    @classmethod
    def __block_text(
        cls, block: Block, config: BaseChunkerConfig, caption: str | None
    ) -> tuple[str, bool] | None:
        """A block's textual contribution → (text, atomic), or None when it contributes nothing."""
        # 1. A table renders to markdown, atomically by default, its caption folded in above.
        if block.block_type == BlockType.TABLE:
            if not config.include_tables or block.table is None or not block.table.cells:
                return None
            rendered = ChunkerHelpers.render_table(block.table)
            text = f"{caption}\n{rendered}" if caption else rendered
            return text, config.tables_atomic
        # 2. THE figure rule: the image and its meaning travel as ONE unit, rendered as an
        #    explicitly MARKED block (leading `[Image]`, OCR labelled) so machine-derived text
        #    never reads as prose; an empty figure (e.g. decorative) contributes nothing.
        if block.block_type == BlockType.FIGURE:
            if not config.include_figures or block.figure is None:
                return None
            text = ChunkerHelpers.render_figure(block.figure, caption, block.text)
            return (text, config.figures_atomic) if text else None
        # 3. Every other block — header/footer furniture included — contributes its native text.
        if block.text and block.text.strip():
            return block.text.strip(), False
        return None

    @classmethod
    def project(cls, ir: DocumentIR, config: BaseChunkerConfig) -> list[Passage]:
        """
        Flatten the enriched IR into the ordered passage list all methods consume.

        Args:
            ir (DocumentIR): The ENRICHED document (figure descriptions aboard).
            config (BaseChunkerConfig): The shared composition rules.

        Returns:
            list[Passage]: Reading-ordered passages, token-counted, section-tagged.
        """
        # 1. Reading order + parent index for the ancestry walks; captions claimed by their unit.
        blocks = sorted(ir.blocks, key=lambda block: block.reading_order)
        by_id = {block.id: block for block in blocks}
        captions = cls.__attach_captions(blocks)
        consumed_captions = {caption.id for caption in captions.values()}

        # 2. One passage per contributing block, rules applied; a fused caption contributes its
        #    block id and page span to the unit that absorbed it.
        passages: list[Passage] = []
        for block in blocks:
            if block.id in consumed_captions:
                continue
            caption_block = captions.get(block.id)
            caption = caption_block.text.strip() if caption_block and caption_block.text else None
            contribution = cls.__block_text(block, config, caption)
            if contribution is None:
                continue
            text, atomic = contribution
            heading_path, section_key = cls.__ancestry(block, by_id)
            unit_blocks = [block] if caption_block is None else sorted(
                [caption_block, block], key=lambda member: member.reading_order
            )
            passages.append(
                Passage(
                    text=text,
                    block_ids=[member.id for member in unit_blocks],
                    heading_path=heading_path,
                    section_key=section_key,
                    atomic=atomic,
                    token_count=ChunkerHelpers.count_tokens(text, config.tokenizer_encoding),
                    role=cls.__role_for(block, heading_path),
                    page_start=min(member.provenance.page for member in unit_blocks),
                    page_end=max(member.provenance.page for member in unit_blocks),
                )
            )
        return passages


__all__ = ["Passage", "PassageProjector"]
