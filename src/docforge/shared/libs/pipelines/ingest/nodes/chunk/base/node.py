# ====== Code Summary ======
# BaseChunkerNode — the abstract base of every chunking method. The shared frame: project the
# enriched IR into passages (the composition rules, applied ONCE for all methods), hand the BODY
# passages to the method's `_split` hook (which only decides the GROUPING), keep the furniture
# (header/footer, toc) passages as small per-role/per-page chunks OUTSIDE the method (never mixed
# into a body chunk), then finalise every group into a Chunk (id, ordinal, joined text, block
# union, token recount, section, page span, role). A method is thus ~one algorithm, nothing else.

# ====== Standard Library Imports ======
import asyncio
from abc import abstractmethod

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode
from shared_libs.public_models import Chunk, ChunkRole, DocumentIR

# ====== Local Project Imports ======
from .config import BaseChunkerConfig
from .helpers import ChunkerHelpers
from .io import ChunkerConsumes, ChunkerProduces
from .passages import Passage, PassageProjector


class BaseChunkerNode(ActionNode):
    """Abstract chunking method: passages in, passage GROUPS out; the base does the rest."""

    Consumes = ChunkerConsumes
    Produces = ChunkerProduces

    @abstractmethod
    async def _split(self, passages: list[Passage]) -> list[list[Passage]]:
        """Group the ordered passages into chunks-to-be — the method's whole personality."""
        ...

    def _overlap_seed(self, group: list[Passage], overlap_tokens: int) -> list[Passage]:
        """
        The trailing passages of a closed group that seed the next one (overlap).

        Args:
            group (list[Passage]): The group just closed.
            overlap_tokens (int): Token budget the repeated tail may use.

        Returns:
            list[Passage]: The tail passages fitting the budget, in reading order.
        """
        seed: list[Passage] = []
        taken = 0
        for passage in reversed(group):
            if taken + passage.token_count > overlap_tokens:
                break
            seed.insert(0, passage)
            taken += passage.token_count
        return seed

    @staticmethod
    def __common_heading_path(group: list[Passage]) -> list[str]:
        """
        The heading_path all passages in a group share — their common section ancestry.

        A single-section group returns that section's exact path (every passage shares it). A
        coalesced multi-section group returns only the shared ancestor prefix — `[]` when the
        sections are unrelated (e.g. sibling level-1 sections) — so the chunk never falsely claims
        to live under the first passage's section. Ancestry is compared by section_key IDENTITY
        (heading ids), not by heading TEXT, since two distinct sections may share a title.

        Args:
            group (list[Passage]): The passages of one chunk-to-be, in reading order.

        Returns:
            list[str]: The common heading-path prefix (texts), top-down.
        """
        # 1. Shrink a shared depth down to the shortest common section_key prefix in the group.
        reference = group[0]
        depth = len(reference.section_key)
        for passage in group[1:]:
            common = 0
            for ref_id, other_id in zip(reference.section_key, passage.section_key):
                if ref_id != other_id:
                    break
                common += 1
            depth = min(depth, common)
            if depth == 0:
                break
        # 2. Project that identity depth onto the first passage's heading TEXTS.
        return reference.heading_path[:depth]

    def __absorb_orphan_headings(self, body: list[Passage]) -> list[Passage]:
        """
        Fold every heading-only passage into a neighbour so no bare title becomes body prose.

        A heading whose section OWNS real content is redundant as body text: its title is already
        carried by the heading_path the breadcrumb renders, so it contributes NO prose — only its
        block id travels forward (provenance) onto the section's first kept passage, never a
        repeated leaf title. A bare heading whose section holds no real content (a stray duplicate
        title, a heading above an empty section) has no such carrier, so it is folded FORWARD as a
        breadcrumb onto the next kept passage; a trailing orphan merges BACKWARD so its title is
        never lost.

        Args:
            body (list[Passage]): The body passages, in reading order.

        Returns:
            list[Passage]: The body with heading-only passages folded into their neighbours.
        """
        # 1. A heading id owns a section only when non-heading content lives under it.
        owned = {sid for passage in body if not passage.heading_only for sid in passage.section_key}
        # 2. Walk the body: an owned heading yields only its block id (no double title); an orphan
        #    heading is carried forward as text; real passages absorb both pending contributions.
        kept: list[Passage] = []
        pending: Passage | None = None
        carried_ids: list[str] = []
        for passage in body:
            if passage.heading_only:
                if passage.section_key and passage.section_key[-1] in owned:
                    carried_ids.extend(passage.block_ids)
                else:
                    pending = self.__fold_headings(pending, passage)
                continue
            passage = passage if pending is None else self.__prepend_heading(pending, passage)
            kept.append(self.__carry_ids(passage, carried_ids))
            pending, carried_ids = None, []
        # 3. Trailing pendings have no forward target — merge the orphan text backward, keep the
        #    owned block ids as provenance on the last kept passage (else both are dropped).
        if pending is not None and kept:
            kept[-1] = self.__append_heading(kept[-1], pending)
        elif pending is not None:
            # A degenerate all-headings, no-body document: there is no neighbour to fold into, so the
            # accumulated heading text becomes a chunk of its own — else the whole document would
            # project to zero chunks and index nothing.
            kept.append(pending)
        if carried_ids and kept:
            kept[-1] = self.__carry_ids(kept[-1], carried_ids)
        return kept

    @staticmethod
    def __carry_ids(passage: Passage, block_ids: list[str]) -> Passage:
        """Prepend carried owned-heading block ids onto a passage (provenance only, no added text)."""
        if not block_ids:
            return passage
        return passage.model_copy(update={"block_ids": [*block_ids, *passage.block_ids]})

    def __fold_headings(self, pending: Passage | None, orphan: Passage) -> Passage:
        """Accumulate consecutive orphan headings into one carried unit (exact duplicates dropped)."""
        if pending is None:
            return orphan
        if ChunkerHelpers.normalize_text(orphan.text) == ChunkerHelpers.normalize_text(
            pending.text
        ):
            return pending
        return self.__join(pending, orphan, f"{pending.text}\n{orphan.text}", lead=pending)

    def __prepend_heading(self, heading: Passage, passage: Passage) -> Passage:
        """Prefix a carried heading as the passage's breadcrumb (skipped when it duplicates it)."""
        if ChunkerHelpers.normalize_text(heading.text) == ChunkerHelpers.normalize_text(
            passage.text.split("\n", 1)[0]
        ):
            return self.__join(heading, passage, passage.text, lead=passage)
        return self.__join(heading, passage, f"{heading.text}\n\n{passage.text}", lead=passage)

    def __append_heading(self, passage: Passage, heading: Passage) -> Passage:
        """Merge a trailing orphan heading backward onto the previous passage so its title survives."""
        return self.__join(passage, heading, f"{passage.text}\n\n{heading.text}", lead=passage)

    def __join(self, first: Passage, second: Passage, text: str, lead: Passage) -> Passage:
        """Merge two passages into ``lead``'s identity with an explicit text and recounted tokens."""
        config: BaseChunkerConfig = self.config
        return lead.model_copy(
            update={
                "text": text,
                "block_ids": [*first.block_ids, *second.block_ids],
                "token_count": ChunkerHelpers.count_tokens(text, config.tokenizer_encoding),
                "page_start": min(first.page_start, second.page_start),
                "page_end": max(first.page_end, second.page_end),
            }
        )

    @staticmethod
    def __group_furniture(furniture: list[Passage]) -> list[list[Passage]]:
        """
        Group furniture passages into one small chunk per (role, page).

        Furniture (header/footer, toc) is disabled-by-role, so it must never be packed into a
        body chunk nor pollute a method's grouping — but it is KEPT (reversible, inspectable).
        A running header/footer has no single reading position (it repeats per page), so the
        page is the natural, provenance-preserving granularity; a ToC spanning several pages
        yields one small chunk per page likewise. Groups keep their first-appearance order.

        Args:
            furniture (list[Passage]): The non-body passages, in reading order.

        Returns:
            list[list[Passage]]: One homogeneous-role group per (role, page), document-ordered.
        """
        buckets: dict[tuple[ChunkRole, int], list[Passage]] = {}
        for passage in furniture:
            buckets.setdefault((passage.role, passage.page_start), []).append(passage)
        return list(buckets.values())

    @staticmethod
    def __assemble_text(group: list[Passage], common: list[str]) -> str:
        """
        Join the group's passages, labelling each COALESCED section not covered by the breadcrumb.

        A single-section chunk's section is already named by its heading_path (the breadcrumb renders
        it), so nothing is inlined. But a coalesced multi-section chunk reports only the COMMON
        heading_path prefix (``[]`` for sibling sections), so its merged sections would otherwise be
        anonymous in the text — a glossary's four terms or a policy's four articles collapsing into
        one unlabelled blob, unretrievable by term/article. Each section whose path extends BEYOND
        the common prefix gets its own heading trail inlined once, at its first passage, so every
        merged section stays identifiable and searchable.

        Args:
            group (list[Passage]): The passages of one chunk-to-be, in reading order.
            common (list[str]): The chunk's common heading-path prefix (what the breadcrumb renders).

        Returns:
            str: The assembled chunk text, coalesced-section headings inlined.
        """
        depth = len(common)
        parts: list[str] = []
        last_key: list[str] | None = None
        for passage in group:
            if passage.section_key != last_key and len(passage.section_key) > depth:
                # A section whose headings are all blank (a heading block with empty text) yields an
                # empty label — skip it rather than inline a stray "" / dangling separator.
                label = " › ".join(level for level in passage.heading_path[depth:] if level.strip())
                if label:
                    parts.append(label)
            parts.append(passage.text)
            last_key = passage.section_key
        return "\n\n".join(parts)

    def __finalize(self, ir: DocumentIR, groups: list[list[Passage]]) -> list[Chunk]:
        """Turn each passage group into a Chunk (role taken from the homogeneous group)."""
        config: BaseChunkerConfig = self.config
        chunks: list[Chunk] = []
        for group in groups:
            if not group:
                continue
            # 1. Join the group's text — labelling each coalesced section the common breadcrumb does
            #    not cover; recount on the FINAL text (labels + joins add tokens).
            common_path = self.__common_heading_path(group)
            text = self.__assemble_text(group, common_path)
            # 2. Union of blocks in reading order, deduplicated (overlap may repeat passages).
            block_ids = list(dict.fromkeys(bid for passage in group for bid in passage.block_ids))
            chunks.append(
                Chunk(
                    chunk_id=f"{ir.doc_id}#c{len(chunks)}",
                    ordinal=len(chunks),
                    text=text,
                    block_ids=block_ids,
                    token_count=ChunkerHelpers.count_tokens(text, config.tokenizer_encoding),
                    heading_path=common_path,
                    role=group[0].role,
                    page_start=min(passage.page_start for passage in group),
                    page_end=max(passage.page_end for passage in group),
                )
            )
        return chunks

    async def run(self, data: ChunkerConsumes) -> ChunkerProduces:
        """
        Chunk the enriched IR with this method.

        Args:
            data (ChunkerConsumes): The ENRICHED IR.

        Returns:
            ChunkerProduces: The raw chunks, in reading order.
        """
        # 1. Warm the tokenizer OFF the event loop — its first load may fetch BPE data over the
        #    network, which must never block the loop nor fail mid-projection.
        config: BaseChunkerConfig = self.config
        await asyncio.to_thread(ChunkerHelpers.count_tokens, "", config.tokenizer_encoding)

        # 2. The shared projection: composition rules applied once, whatever the method.
        passages = PassageProjector.project(data.ir, config)
        if not passages:
            self.logger.warning(f"Document '{data.ir.doc_id}' projected to zero passages")
            return ChunkerProduces(chunks=[])

        # 3. Only BODY passages flow through the method's grouping; furniture (header/footer, toc,
        #    boilerplate) is kept as its own small per-role/per-page chunks, never mixed into a body
        #    chunk. Orphan headings (bare titles with no section of their own) are folded into a
        #    neighbour first, so no heading becomes a standalone one-line chunk.
        body = self.__absorb_orphan_headings(
            [passage for passage in passages if passage.role is ChunkRole.BODY]
        )
        furniture = [passage for passage in passages if passage.role is not ChunkRole.BODY]
        groups = await self._split(body)
        groups.extend(self.__group_furniture(furniture))

        # 4. Finalise into chunks. NOTE: caps are SOFT at the join margin — packing sums the
        #    passages' counts, and the "\n\n" joins add a few tokens; token_count is the honest
        #    recount on the final text.
        chunks = self.__finalize(data.ir, groups)
        self.logger.info(
            f"Chunked '{data.ir.doc_id}': {len(passages)} passage(s) -> {len(chunks)} chunk(s) "
            f"({len(furniture)} furniture passage(s) kept as disabled-by-role chunks)"
        )
        return ChunkerProduces(chunks=chunks)


__all__ = ["BaseChunkerNode"]
