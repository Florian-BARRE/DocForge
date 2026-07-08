# ====== Code Summary ======
# BaseOcrNode — the abstract base of every OCR provider, a PER-ITEM node: it reads one figure's
# crop and relays the figure with its ``read_text`` filled, scored by the provider's confidence.
# Escalation is pure graph: a ScoreBelow (or OnFailure) transition to the next provider; the
# convergence back is a FromFirst binding. Children implement ONLY `_read(image)`.

# ====== Standard Library Imports ======
from abc import abstractmethod

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode

# ====== Local Project Imports ======
from .io import OcrConsumes, OcrProduces


class BaseOcrNode(ActionNode):
    """Abstract OCR provider: one figure in, the read figure out; children implement _read."""

    Consumes = OcrConsumes
    Produces = OcrProduces

    @abstractmethod
    async def _read(self, image: bytes) -> tuple[str, float]:
        """Run the provider's OCR on one image → (text, confidence in [0, 1])."""
        ...

    async def run(self, data: OcrConsumes) -> OcrProduces:
        """
        Read the figure's crop and relay the figure with its read_text filled.

        Args:
            data (OcrConsumes): The figure to read.

        Returns:
            OcrProduces: An updated COPY of the figure (instances are shared across concurrent
            items) with ``read_text`` set to the reading, scored by the provider's confidence.
        """
        # 1. Run the provider's engine on the crop.
        text, score = await self._read(data.figure.image)
        self.logger.debug(f"OCR '{self.KIND}' read {len(text)} chars (score {score:.2f})")

        # 2. Relay an updated copy — the item itself is never mutated.
        return OcrProduces(figure=data.figure.model_copy(update={"read_text": text}), score=score)


__all__ = ["BaseOcrNode"]
