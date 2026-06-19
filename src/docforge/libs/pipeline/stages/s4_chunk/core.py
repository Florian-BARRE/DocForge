# ====== Code Summary ======
# S4ChunkStage — heading-hierarchy-aware chunking stage orchestrator.
# Wires HeadingWalker (skeleton + caption map) and ChunkAssembler (flat / hierarchical)
# into the run() pipeline.  Config hashing and the Merkle fingerprint helper live here
# because they depend on the stage's own parameters.

# ====== Standard Library Imports ======
from __future__ import annotations

import hashlib
import itertools
import json
import re
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass

from libs.config.pipeline import AtomicConfig

# ====== Internal Project Imports ======
from libs.domain.ir.models import DocumentIR

from .helpers.linker import CrossReferenceLinker
from .strategies.base import SectionSplitter
from .strategies.token_budget import TokenBudgetSplitter
from .assemblers.base import ChunkAssembler
from .heading_walker import HeadingWalker

# ====== Local Project Imports ======
from .models import _PARENT_STRATEGY, S4Result


class S4ChunkStage(LoggerClass):
    """
    S4 — Heading-hierarchy-aware chunker.

    Pipeline per document:
    1. Build the heading skeleton (parser headings + regex promotion rules) and group content
       into sections; emit atomic figures/tables (with co-located captions) at their position.
    2. Flat mode: pack small sibling sections together up to the token budget and split oversize
       sections with the configured split method.  Hierarchical mode: each divided section yields
       a parent chunk over its children (parent_id set).
    3. Link cross-references (see Figure 3 / Article 5) to the chunks that hold them.
    """

    def __init__(
        self,
        *,
        splitter: SectionSplitter | None = None,
        heading_rules: list[Any] | None = None,
        reinject_breadcrumb: bool = True,
        merge_short_sections: bool = True,
        atomic: AtomicConfig | None = None,
        cross_references: bool = True,
        hierarchical: bool = False,
    ) -> None:
        """
        Initialize the chunking stage.

        Args:
            splitter (SectionSplitter | None): Intra-section split method. None → a default
                TokenBudgetSplitter with its own defaults.
            heading_rules (list | None): Ordered HeadingRule-like objects (``.level``, ``.pattern``)
                promoting text to headings.  None → parser headings only.
            reinject_breadcrumb (bool): Record the section breadcrumb on each chunk so split
                sub-chunks remain section-aware (consumed by S5 for embed_text).
            merge_short_sections (bool): Pack small sibling sections together (flat mode only).
            atomic (AtomicConfig | None): Atomic-block policy (tables/figures/formulas/captions).
            cross_references (bool): Run the cross-reference linking pass.
            hierarchical (bool): Emit a parent chunk per divided section over its children.
        """
        LoggerClass.__init__(self)
        self._splitter: SectionSplitter = splitter or TokenBudgetSplitter()
        self._reinject = reinject_breadcrumb
        self._merge_short = merge_short_sections
        self._atomic = atomic or AtomicConfig()
        self._cross_references = cross_references
        self._hierarchical = hierarchical
        self._max_tokens = self._splitter.max_tokens
        # Compile (level, regex) rules once; skip patterns that fail to compile.
        self._rules: list[tuple[int, re.Pattern]] = []
        for rule in heading_rules or []:
            try:
                self._rules.append((int(rule.level), re.compile(rule.pattern)))
            except (re.error, AttributeError, ValueError):
                self.logger.warning(f"S4: skipping invalid heading rule {rule!r}")
        self._config_hash = self._compute_config_hash(heading_rules or [])

    def params_for_fingerprint(self) -> dict[str, Any]:
        """
        Return chunking parameters for the S4 Merkle fingerprint.

        Returns:
            dict[str, Any]: Configuration dictionary used for hashing.
        """
        return self._config_dict([(lvl, rx.pattern) for lvl, rx in self._rules])

    async def run(self, ir: DocumentIR) -> S4Result:
        """
        Chunk all blocks in the enriched DocumentIR using heading-hierarchy awareness.

        Args:
            ir (DocumentIR): Enriched DocumentIR from S2.

        Returns:
            S4Result: Chunks in reading order, each tagged with its section breadcrumb.
        """
        self.logger.info(
            f"S4 started: doc_id={ir.doc_id} blocks={len(ir.blocks)} "
            f"method={self._splitter.name} hierarchical={self._hierarchical} rules={len(self._rules)}"
        )

        # 1. Map captions onto their atomic figure/table, then collect ordered items
        consumed_caption_ids, caption_of = HeadingWalker.caption_map(
            ir.blocks, self._atomic, self._rules
        )
        items = HeadingWalker.collect_items(
            ir.blocks, consumed_caption_ids, self._atomic, self._rules
        )

        # 2. Deterministic ordinal stream for stable, collision-free chunk ids
        counter = itertools.count()

        # 3. Build chunks (flat packing vs. hierarchical parent/children)
        if self._hierarchical:
            chunks = await ChunkAssembler.process_hierarchical(
                items, ir.doc_id, caption_of, counter, self._splitter, self._config_hash
            )
        else:
            chunks = await ChunkAssembler.process_flat(
                items, ir.doc_id, caption_of, counter, self._splitter, self._merge_short, self._config_hash
            )

        # 4. Cross-reference linking (Axe 4) — best-effort, mutates prov in place
        if self._cross_references:
            CrossReferenceLinker().link(chunks)

        # 5. Tally counts by chunk kind
        n_figure = sum(1 for c in chunks if c.strategy == "figure")
        n_table = sum(1 for c in chunks if c.strategy == "table")
        n_parent = sum(1 for c in chunks if c.strategy == _PARENT_STRATEGY)
        n_text = len(chunks) - n_figure - n_table - n_parent

        result = S4Result(
            chunks=chunks,
            config_hash=self._config_hash,
            n_text_chunks=n_text,
            n_figure_chunks=n_figure,
            n_table_chunks=n_table,
            n_parent_chunks=n_parent,
        )
        self.logger.info(
            f"S4 done: doc_id={ir.doc_id} chunks={len(chunks)} "
            f"(text={n_text} figure={n_figure} table={n_table} parent={n_parent})"
        )
        return result

    # ─── Config hashing ────────────────────────────────────────────────────────

    def _config_dict(self, heading_rules: list[Any]) -> dict[str, Any]:
        """
        Assemble the full configuration dict used for the deterministic hash + fingerprint.

        Args:
            heading_rules (list[Any]): Either compiled (level, pattern) tuples or rule-like objects.

        Returns:
            dict[str, Any]: Configuration dictionary.
        """
        # heading_rules may be (level, pattern) tuples (from compiled rules) or rule-like objects.
        rules: list[dict[str, Any]] = []
        for r in heading_rules:
            if isinstance(r, tuple):
                rules.append({"level": r[0], "pattern": r[1]})
            else:
                rules.append({"level": getattr(r, "level", None), "pattern": getattr(r, "pattern", None)})
        return {
            "split_method": self._splitter.signature(),
            "reinject_breadcrumb": self._reinject,
            "merge_short_sections": self._merge_short,
            "hierarchical": self._hierarchical,
            "cross_references": self._cross_references,
            "atomic": self._atomic.model_dump(),
            "heading_rules": rules,
        }

    def _compute_config_hash(self, heading_rules: list[Any]) -> str:
        """
        Compute a deterministic hash of the chunking configuration.

        Args:
            heading_rules (list[Any]): Raw heading rules (before compilation).

        Returns:
            str: Hex digest (blake2b, 16 bytes) of the serialised config.
        """
        config_str = json.dumps(self._config_dict(heading_rules), sort_keys=True)
        return hashlib.blake2b(config_str.encode(), digest_size=16).hexdigest()
