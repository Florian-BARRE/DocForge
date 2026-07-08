# ====== Code Summary ======
# BaseVlmNode — the abstract base of every VLM provider, a PER-ITEM node closing an enrich branch:
# it describes one figure (the crop, plus the OCR text already in the figure's ``read_text``) and
# emits the branch's terminal EnrichmentEntry. The base composes the instruction (system prompt +
# the chart-to-table request when enabled) and post-processes the answer (table block parsed into
# rows and stripped). Children implement ONLY `_describe(image, context, system_prompt)`.

# ====== Standard Library Imports ======
from abc import abstractmethod

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode
from shared_libs.public_models import EnrichmentEntry

# ====== Local Project Imports ======
from .config import BaseVlmConfig
from .helpers import BaseVlmHelpers
from .io import VlmConsumes, VlmProduces

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
        Describe the figure and close the branch with its EnrichmentEntry.

        Args:
            data (VlmConsumes): The figure to describe.

        Returns:
            VlmProduces: The terminal entry (kind + OCR text carried over, description filled,
            table rows when requested).
        """
        config: BaseVlmConfig = self.config
        # 1. The system prompt IS the behaviour; chart-to-table appends its output contract.
        prompt = config.system_prompt + (_TABLE_INSTRUCTION if config.extract_table else "")

        # 2. Run the provider.
        answer, _confidence = await self._describe(data.figure.image, data.figure.read_text, prompt)

        # 3. Post-process: pull the table rows out of the answer when they were requested.
        description, data_table = (
            BaseVlmHelpers.extract_table(answer) if config.extract_table else (answer.strip(), None)
        )

        # 4. Close the branch: everything the figure's run learned, in one entry.
        return VlmProduces(
            entry=EnrichmentEntry(
                block_id=data.figure.block_id,
                kind=data.figure.kind,
                ocr_text=data.figure.read_text or None,
                description=description or None,
                data_table=data_table,
            )
        )


__all__ = ["BaseVlmNode"]
