# ====== Code Summary ======
# BaseVlmNode — the abstract base of every VLM provider, a PER-ITEM node describing one figure (the
# crop, plus the OCR text already in the figure's ``read_text``) into an EnrichmentEntry scored by
# the provider's confidence. The base composes the instruction (system prompt + the chart-to-table
# request when enabled) and post-processes the answer (table block parsed into rows and stripped).
# Escalation is pure graph: a ScoreBelow (or OnFailure) transition to the next provider, closed on a
# model-free ``vlm_entry`` terminal fed best-first. Children implement ONLY `_describe(...)`.

# ====== Standard Library Imports ======
import asyncio
from abc import abstractmethod

# ====== Third-Party Library Imports ======
import httpx
import openai

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode
from shared_libs.pipelines.nodes.openai_compat import UsageAccumulator
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
    async def _describe(
        self,
        image: bytes,
        context: str,
        system_prompt: str,
        usage_sink: UsageAccumulator | None = None,
    ) -> tuple[str, float]:
        """Run the provider's VLM on one image (+ text context) → (answer, confidence in [0, 1]).

        Args:
            image (bytes): The figure crop to describe.
            context (str): Textual context (e.g. the figure's prior OCR text).
            system_prompt (str): The composed instruction driving the description.
            usage_sink (UsageAccumulator | None): The per-run accumulator to attach to the paid chat
                call so EVERY attempt's token usage is summed (not just the final success). One sink
                is threaded across the whole retry loop; ``None`` disables usage capture.
        """
        ...

    @staticmethod
    def _is_transient(error: Exception) -> bool:
        """Whether a VLM provider error is worth retrying: a timeout, a connection blip, or a 429/5xx.

        VLM calls are paid, so the retryable set is deliberately narrow. A concrete child runs its
        call through LangChain's ChatOpenAI, whose failures surface as ``openai`` SDK errors — a
        timeout / connection error, a rate limit (429) or a 5xx server error are transient and safe
        to repeat; a 4xx (auth, bad request) is a permanent misconfiguration whose retry would only
        waste a paid call, so it is NOT transient (raw ``httpx`` transport/timeout errors are also
        covered for any provider that surfaces them directly). A successful "cannot describe" answer
        is not an exception and never reaches here.
        """
        if isinstance(error, httpx.TimeoutException | httpx.TransportError):
            return True
        return isinstance(
            error,
            openai.APITimeoutError
            | openai.APIConnectionError
            | openai.RateLimitError
            | openai.InternalServerError,
        )

    async def _describe_with_retry(
        self,
        image: bytes,
        context: str,
        system_prompt: str,
        usage_sink: UsageAccumulator | None,
    ) -> tuple[str, float]:
        """Call ``_describe`` with a bounded, transient-only retry below the graph's escalation.

        This sits BENEATH the pipeline's own recovery: after the retries are exhausted the error is
        re-raised, so the existing ScoreBelow/OnFailure chaining to the next provider (and the
        figure-skip terminal) still takes over. Only transient failures are retried; a non-transient
        error re-raises immediately. Each attempt is bounded by the provider's ``timeout_seconds``.
        The ONE ``usage_sink`` is passed to every attempt so an attempt that billed then failed still
        contributes its usage (not just the final success).
        """
        config: BaseVlmConfig = self.config
        for attempt in range(config.max_retries + 1):  # 1 initial call + max_retries retries
            try:
                return await self._describe(image, context, system_prompt, usage_sink=usage_sink)
            except Exception as error:  # noqa: BLE001 — re-raised below unless a bounded transient
                if not self._is_transient(error) or attempt == config.max_retries:
                    raise
                self.logger.warning(
                    f"VLM '{self.KIND}' transient error "
                    f"(attempt {attempt + 1}/{config.max_retries + 1}): {error!r}"
                )
                await asyncio.sleep(config.retry_backoff_seconds * (attempt + 1))
        # Unreachable: the loop either returns a result or raises on the final attempt.
        raise AssertionError("unreachable")

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

        # 2. Run the provider (bounded transient retry below the graph's escalation) — the confidence
        #    drives quality escalation, never discarded. ONE accumulator, keyed to the pricing model,
        #    is threaded across every attempt so a paid attempt that billed then retried still counts.
        #    The model id lives on the concrete provider's config (a base VLM config need not carry
        #    one), read defensively so a usage-capture concern can never fail the node.
        usage = UsageAccumulator(getattr(config, "model", ""))
        answer, confidence = await self._describe_with_retry(
            data.figure.image, data.figure.read_text, prompt, usage_sink=usage
        )

        # 3. Post-process: pull the table rows out of the answer when they were requested.
        description, data_table = (
            BaseVlmHelpers.extract_table(answer) if config.extract_table else (answer.strip(), None)
        )

        # 4. Emit the scored entry: everything the figure's run learned, in one entry. The summed
        #    token usage across ALL attempts rides along on the output for the engine to lift (None
        #    when no attempt carried usage — a usage-less provider stays free, unchanged).
        output = VlmProduces(
            entry=EnrichmentEntry(
                block_id=data.figure.block_id,
                kind=data.figure.kind,
                ocr_text=data.figure.read_text or None,
                description=description or None,
                data_table=data_table,
            ),
            score=confidence,
        )
        output._usage = usage.usage
        return output


__all__ = ["BaseVlmNode"]
