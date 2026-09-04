# ====== Code Summary ======
# The figure_classify node — the switch driver of the enrich ForEach body: it decides which of the
# five FigureKind classes one figure belongs to. Cheap heuristics first (full-page crop →
# scanned_text, tiny crop → decorative), then a configurable backend for everything else: the hosted
# VLM (default) OR a fully-local, endpoint-free heuristic classifier (RapidOCR text density +
# geometry). Its output exposes `kind` (what the WhenEquals branches route on) and the stamped figure
# the branches consume; its `score` can gate an escalation regardless of the backend.

# ====== Standard Library Imports ======
import base64

from langchain_core.messages import HumanMessage, SystemMessage

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeInput, ScoredOutput
from shared_libs.pipelines.nodes.ocr.rapidocr import RapidOcrEngine
from shared_libs.pipelines.nodes.openai_compat import EndpointReachability, OpenAICompatHelpers
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import FigureItem, FigureKind, figure_prompt_lines

# ====== Local Project Imports ======
from .config import FigureClassifyConfig
from .helpers import FigureClassifyHelpers
from .local import LocalFigureClassifierHelpers

# The classification instruction: one word among the classes, nothing else. The per-class lines are
# DERIVED from the single-source figure routing, so the prompt never drifts from FigureKind.
_CLASSIFY_PROMPT = (
    "Classify this image into EXACTLY ONE of these classes and answer with that single word:\n"
    + figure_prompt_lines()
)

# Confidence granted to a heuristic decision (high: the geometric evidence is strong).
_HEURISTIC_SCORE = 0.9
# Confidence when the model answer is unusable — low, so a ScoreBelow edge can catch it.
_FALLBACK_SCORE = 0.3


class FigureClassifyConsumes(NodeInput):
    """Input: the figure to classify."""

    figure: FigureItem = Field(description="The figure to classify (crop + page coverage).")


class FigureClassifyProduces(ScoredOutput):
    """Output: the stamped figure + the routed ``kind`` (what WhenEquals switches on)."""

    figure: FigureItem = Field(description="The SAME figure, its kind stamped (a copy).")
    kind: str = Field(description="The decided class — what the when_equals branches route on.")


@NodeRegistry.register("enrich")
class FigureClassifyNode(ActionNode):
    """Decide a figure's class — heuristics for the obvious, a vision model for the rest."""

    KIND = "figure_classify"
    NAME = "Figure classify"
    SUMMARY = "Classify a figure (photo / scanned_text / chart / diagram / decorative)."
    HOW_IT_WORKS = (
        "Applies the geometric heuristics first (a crop covering most of the page is a scan; a "
        "tiny crop is decorative), then asks the configured vision model for one class word. The "
        "output kind drives the WhenEquals branches; an unusable model answer degrades to 'photo' "
        "with a LOW score so a ScoreBelow edge can catch it."
    )
    Config = FigureClassifyConfig
    Consumes = FigureClassifyConsumes
    Produces = FigureClassifyProduces
    # The switch driver: the UI offers one when_equals branch per class, ready-made.
    SWITCH_FIELDS = {"kind": [kind.value for kind in FigureKind]}

    async def preflight(self) -> None:
        """Verify the vision endpoint is reachable before any spend — VLM backend only.

        The ``local`` backend makes NO network call (RapidOCR + geometry, endpoint-free), so its
        preflight is a deliberate no-op. Only the ``vlm`` backend reaches a hosted endpoint, so only
        it is probed; an empty/unreachable ``base_url`` on the VLM backend fails HERE, before the
        first classification spends (the reachability sweep picks this node up because it overrides
        the no-op ``ActionNode.preflight``).
        """
        config: FigureClassifyConfig = self.config
        # 1. Local backend has no endpoint to reach — nothing to probe.
        if config.classify_backend == "local":
            return
        # 2. VLM backend — probe the vision endpoint with the dedicated preflight budget.
        await EndpointReachability.check(
            node_kind=self.KIND,
            base_url=config.base_url,
            api_key=config.api_key,
            timeout_seconds=config.preflight_timeout_seconds,
        )

    def __heuristic_kind(self, figure: FigureItem) -> str | None:
        """The geometric fast paths — None when no heuristic applies."""
        config: FigureClassifyConfig = self.config
        # 1. A crop covering (almost) the whole page is a scanned page, not an illustration.
        if figure.page_coverage >= config.full_page_ratio:
            return FigureKind.SCANNED_TEXT.value
        # 2. A tiny crop (logo, rule, bullet) is decoration — not worth a model call.
        dimensions = FigureClassifyHelpers.png_dimensions(figure.image)
        if dimensions is not None and min(dimensions) < config.min_side_px:
            return FigureKind.DECORATIVE.value
        return None

    async def _ask_model(self, image: bytes, prompt: str) -> str:
        """Ask the configured vision model for the class word (overridable hook)."""
        config: FigureClassifyConfig = self.config
        # 1. One multimodal message: the instruction + the image as a data URL.
        encoded = base64.b64encode(image).decode("ascii")
        model = OpenAICompatHelpers.chat(
            config,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            max_retries=config.max_retries,
        )
        answer = await model.ainvoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(
                    content=[
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{encoded}"},
                        }
                    ]
                ),
            ]
        )
        return str(answer.content)

    async def _local_signal(self, image: bytes) -> tuple[str, float, float]:
        """Read the crop's LOCAL text signal (overridable hook) → (text, confidence, coverage).

        Runs the process-shared RapidOCR engine on the crop and measures how much of it confident
        text covers — the fully-local, endpoint-free evidence the local backend classifies on. It is
        the local counterpart of ``_ask_model``: overriding it lets tests inject a synthetic signal.
        """
        # 1. One local OCR pass — the raw readings carry the boxes coverage is measured from.
        readings = await RapidOcrEngine.read(image)
        text, confidence = RapidOcrEngine.to_text(readings)
        # 2. Coverage needs the crop dimensions (read from the PNG header, no decoder).
        dimensions = FigureClassifyHelpers.png_dimensions(image)
        coverage = LocalFigureClassifierHelpers.coverage(readings, dimensions)
        return text, confidence, coverage

    async def __classify_uncertain(self, figure: FigureItem) -> tuple[str, float]:
        """Classify a figure the heuristics could not decide, per the configured backend."""
        config: FigureClassifyConfig = self.config
        # 1. Local backend — fully offline: RapidOCR text density + best-effort visual statistics.
        if config.classify_backend == "local":
            text, confidence, coverage = await self._local_signal(figure.image)
            return LocalFigureClassifierHelpers.decide(
                text, confidence, coverage, figure.image, config
            )
        # 2. VLM backend — ask the vision model for one class word; an unusable answer degrades
        #    LOUDLY in the score (photo is the safest routing: a generic description is never wrong).
        answer = await self._ask_model(figure.image, _CLASSIFY_PROMPT)
        parsed = FigureClassifyHelpers.parse_kind(answer)
        if parsed is None:
            self.logger.warning(f"Unusable classification for '{figure.block_id}': {answer!r}")
        return (parsed or FigureKind.PHOTO.value), (1.0 if parsed is not None else _FALLBACK_SCORE)

    async def run(self, data: FigureClassifyConsumes) -> FigureClassifyProduces:
        """
        Classify the figure and stamp its kind.

        Args:
            data (FigureClassifyConsumes): The figure to classify.

        Returns:
            FigureClassifyProduces: The stamped figure copy + the kind, scored by confidence.
        """
        config: FigureClassifyConfig = self.config

        # 1. Heuristics decide the obvious cases for free.
        kind = self.__heuristic_kind(data.figure) if config.use_heuristics else None
        score = _HEURISTIC_SCORE

        # 2. Everything else goes to the configured backend (hosted VLM or fully-local heuristic).
        if kind is None:
            kind, score = await self.__classify_uncertain(data.figure)

        # 3. Stamp a COPY (items are shared across concurrent runs) and expose the routed kind.
        self.logger.debug(f"Figure '{data.figure.block_id}' classified as '{kind}' ({score:.2f})")
        return FigureClassifyProduces(
            figure=data.figure.model_copy(update={"kind": kind}), kind=kind, score=score
        )


__all__ = ["FigureClassifyNode", "FigureClassifyConsumes", "FigureClassifyProduces"]
