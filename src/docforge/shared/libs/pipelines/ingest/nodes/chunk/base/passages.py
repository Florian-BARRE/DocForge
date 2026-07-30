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
from shared_libs.public_models import TOC_TITLES, Block, BlockType, ChunkRole, DocumentIR

# ====== Local Project Imports ======
from .config import BaseChunkerConfig
from .helpers import ChunkerHelpers

# The table-of-contents heading allow-list is the shared document-structure constant (public_models)
# — one source for the chunker role classifier, the doc_meta anchor and the persistence title
# fallback. BOILERPLATE is NOT allow-list driven: it is inferred structurally from cross-page
# repetition (see ``__repeated_texts``).
_TOC_TITLES = TOC_TITLES


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
        role (ChunkRole): Structural classification of this unit (body / header-footer / toc /
            boilerplate); body by default. Furniture (non-body) passages are kept as disabled
            chunks, never mixed into a body chunk.
        heading_only (bool): True when this unit is a bare section heading with no body of its own
            (a HEADING block's native text, nothing else). Such a unit must never stand alone as a
            chunk — the base node merges an orphan heading forward into the next section.
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
    heading_only: bool = False
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
    def __repeated_texts(blocks: list[Block], config: BaseChunkerConfig) -> frozenset[str]:
        """
        Build the set of normalized texts that recur across enough DISTINCT pages to be boilerplate.

        Repeated inter-page/inter-slide furniture (a fixed objectives list on every slide, a
        recurring notice) has no IR block type, yet it must not be embedded once per page. It is
        inferred here structurally: a text is boilerplate when its normalized form appears on at
        least ``boilerplate_min_pages`` DISTINCT provenance pages (distinct pages, never raw
        occurrences — two copies on one page are not repetition). Exact normalized match keeps it
        conservative; the whole pass is skipped when the knob is off.

        Args:
            blocks (list[Block]): The document's blocks (any order).
            config (BaseChunkerConfig): The chunker config (thresholds + on/off switch).

        Returns:
            frozenset[str]: Normalized texts recurring on >= ``boilerplate_min_pages`` pages.
        """
        # 1. Disabled → nothing is boilerplate; the role is never assigned.
        if not config.detect_repeated_boilerplate:
            return frozenset()
        # 2. Map each normalized text to the SET of pages it appears on (distinct pages only).
        pages_by_text: dict[str, set[int]] = {}
        for block in blocks:
            if not (block.text and block.text.strip()):
                continue
            key = ChunkerHelpers.normalize_text(block.text)
            if key:
                pages_by_text.setdefault(key, set()).add(block.provenance.page)
        # 3. Keep only the texts spanning enough distinct pages to be furniture, not real content.
        return frozenset(
            key
            for key, pages in pages_by_text.items()
            if len(pages) >= config.boilerplate_min_pages
        )

    @staticmethod
    def __role_for(
        block: Block, heading_path: list[str], boilerplate_texts: frozenset[str]
    ) -> ChunkRole:
        """
        Classify a block's structural role from IR signals (conservative, best-effort).

        Header/footer is an explicit IR block type. A table-of-contents is inferred from the
        section a block lives under: any heading in its ancestry whose FULL normalized text is a
        known ToC title (exact match, never substring) marks the whole section — heading and its
        list-like body alike — as scaffolding. Boilerplate is inferred last: a block whose
        normalized text recurs across many pages (precomputed set) is repeated furniture. The more
        specific structural signals (header/footer, ToC) take precedence; everything else is body.

        Args:
            block (Block): The IR block behind the passage.
            heading_path (list[str]): The block's heading ancestry TEXTS, top-down.
            boilerplate_texts (frozenset[str]): Normalized texts flagged as cross-page boilerplate.

        Returns:
            ChunkRole: The structural role of the passage this block produces.
        """
        # 1. Header/footer furniture is labelled directly from the IR block type.
        if block.block_type == BlockType.HEADER_FOOTER:
            return ChunkRole.HEADER_FOOTER
        # 2. A ToC section is inferred from the ancestry — any heading matching a known ToC title.
        if any(heading.strip().lower() in _TOC_TITLES for heading in heading_path):
            return ChunkRole.TOC
        # 3. Repeated cross-page text is boilerplate — kept, but disabled-by-role (never embedded).
        if block.text and ChunkerHelpers.normalize_text(block.text) in boilerplate_texts:
            return ChunkRole.BOILERPLATE
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
        # 1. Reading order + parent index for the ancestry walks; captions claimed by their unit;
        #    the cross-page repetition set precomputed once for the boilerplate role.
        blocks = sorted(ir.blocks, key=lambda block: block.reading_order)
        by_id = {block.id: block for block in blocks}
        captions = cls.__attach_captions(blocks)
        consumed_captions = {caption.id for caption in captions.values()}
        boilerplate_texts = cls.__repeated_texts(blocks, config)

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
                # The owning figure/table contributed nothing (empty table, figures disabled, no
                # crop) — but its caption was already CONSUMED. Keep the caption as this unit's body
                # (both the caption block and the figure/table it labels stay in provenance) so its
                # text is never silently lost.
                if caption is None:
                    continue
                contribution = (caption, False)
            text, atomic = contribution
            heading_path, section_key = cls.__ancestry(block, by_id)
            unit_blocks = (
                [block]
                if caption_block is None
                else sorted([caption_block, block], key=lambda member: member.reading_order)
            )
            passages.append(
                Passage(
                    text=text,
                    block_ids=[member.id for member in unit_blocks],
                    heading_path=heading_path,
                    section_key=section_key,
                    atomic=atomic,
                    token_count=ChunkerHelpers.count_tokens(text, config.tokenizer_encoding),
                    role=cls.__role_for(block, heading_path, boilerplate_texts),
                    heading_only=block.block_type == BlockType.HEADING,
                    page_start=min(member.provenance.page for member in unit_blocks),
                    page_end=max(member.provenance.page for member in unit_blocks),
                )
            )
        return passages


__all__ = ["Passage", "PassageProjector"]
