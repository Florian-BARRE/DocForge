# ====== Code Summary ======
# BaseVlmNode — the abstract base of every VLM provider, a PER-ITEM node describing one figure (the
# crop, plus the OCR text already in the figure's ``read_text``) into an EnrichmentEntry scored by
# the provider's confidence. The base composes the instruction (system prompt + the chart-to-table
# request when enabled) and post-processes the answer (table block parsed into rows and stripped).
# Escalation is pure graph: a ScoreBelow (or OnFailure) transition to the next provider, closed on a
# model-free ``vlm_entry`` terminal fed best-first. Children implement ONLY `_describe(...)`.

# ====== Standard Library Imports ======
from abc import abstractmethod

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode
from shared_libs.public_models import EnrichmentEntry

# ====== Local Project Imports ======
from .config import BaseVlmConfig
from .helpers import BaseVlmHelpers
from .io import VlmConsumes, VlmProduces

# Prepended to EVERY figure system prompt — a node-level invariant, not a per-collection knob.
# A chat VLM left to itself falls into assistant mode on an unlabelled figure (a bar chart with no
# printed values): it addresses the user and asks them to "share the data" instead of describing
# what it sees, and that deflection text then gets embedded verbatim as chunk content. The guard
# forces a standalone visual description and forbids every deflection an assistant would emit.
_DESCRIPTION_GUARD = (
    "You are a vision description engine indexing figures for retrieval. Describe ONLY what is "
    "visually present, as a self-contained passage. NEVER address a reader, NEVER ask for more "
    "information or data, NEVER offer to help, and NEVER state that you cannot see the values — you "
    "always can. When exact numbers or categories are not printed on the figure, describe the "
    "visual pattern instead: the number of bars, series, slices or lines, their relative heights or "
    "proportions, the overall trend, and any title, legend, axis labels or meaningful colours; give "
    "approximate or relative magnitudes rather than refusing. Output the description text only."
)

# Appended to the system prompt when chart-to-table extraction is enabled.
_TABLE_INSTRUCTION = (
    "\n\nAdditionally, END your answer with the underlying data as rows inside a fenced block:\n"
    "```table\nheader1 | header2 | ...\nvalue1 | value2 | ...\n```"
)


class BaseVlmNode(ActionNode):
    """Abstract VLM provider: one figure in, its entry out; children implement _describe."""

    Consumes = VlmConsumes
    Produces = VlmProduces

    @abstractmethod
    async def _describe(self, image: bytes, context: str, system_prompt: str) -> tuple[str, float]:
        """Run the provider's VLM on one image (+ text context) → (answer, confidence in [0, 1])."""
        ...

    async def run(self, data: VlmConsumes) -> VlmProduces:
        """
        Describe the figure and emit its EnrichmentEntry, scored by the provider's confidence.

        Args:
            data (VlmConsumes): The figure to describe.

        Returns:
            VlmProduces: The entry (kind + OCR text carried over, description filled, table rows
            when requested), scored by the provider's self-assessed confidence — what a score_below
            escalation edge compares to its threshold.
        """
        config: BaseVlmConfig = self.config
        # 1. The always-on guard rail frames the behaviour, the per-class prompt drives it, and
        #    chart-to-table appends its output contract. The guard is a node invariant: it is never
        #    removable by config, so a user's custom prompt cannot reopen the deflection failure mode.
        prompt = f"{_DESCRIPTION_GUARD}\n\n{config.system_prompt}" + (
            _TABLE_INSTRUCTION if config.extract_table else ""
        )

        # 2. Run the provider — the confidence drives quality escalation, never discarded.
        answer, confidence = await self._describe(data.figure.image, data.figure.read_text, prompt)

        # 3. Post-process: pull the table rows out of the answer when they were requested.
        description, data_table = (
            BaseVlmHelpers.extract_table(answer) if config.extract_table else (answer.strip(), None)
        )

        # 4. Emit the scored entry: everything the figure's run learned, in one entry.
        return VlmProduces(
            entry=EnrichmentEntry(
                block_id=data.figure.block_id,
                kind=data.figure.kind,
                ocr_text=data.figure.read_text or None,
                description=description or None,
                data_table=data_table,
            ),
            score=confidence,
        )


__all__ = ["BaseVlmNode"]
