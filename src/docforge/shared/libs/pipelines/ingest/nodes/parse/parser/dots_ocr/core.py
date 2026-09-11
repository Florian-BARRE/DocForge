# ====== Code Summary ======
# The dots.ocr parser node — a NETWORK client, not an in-process engine. It POSTs the PDF bytes to a
# sidecar (src/dots_ocr_server, POST /parse) that renders each page to an image, sends it to the
# dots.ocr per-element layout VLM (rednote-hilab/dots.ocr, served by vLLM on its own torch+CUDA
# runtime), and returns the shared per-page block contract, which DotsOcrIRMapper maps into the
# canonical IR. Subclasses BaseParserNode directly (no docling engine): it inherits the PDF-view
# resolution, empty-IR degradation, quality score and ScoredOutput, and implements ONLY _parse (async
# network I/O) plus preflight (endpoint reachability). Wire it as an OFF-by-default ScoreBelow
# escalation head after standard docling, never in the default/light blob — the sidecar's VLM is
# GPU-only, heavy, slow and optional (built lazily sidecar-side).

# ====== Third-Party Library Imports ======
import httpx

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.http_pool import HttpClientPool
from shared_libs.pipelines.nodes.openai_compat import EndpointReachability
from shared_libs.pipelines.nodes.retry import NetworkRetry
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import DocumentIR, IntakeResult

# ====== Local Project Imports ======
from ..base import BaseParserNode
from .config import ParserDotsOcrConfig
from .mapper import DotsOcrIRMapper


@NodeRegistry.register("parser")
class ParserDotsOcrNode(BaseParserNode):
    """
    Parse a PDF with the dots.ocr sidecar, mapping its per-element layout output to the canonical IR.

    A compact (3B) per-element layout VLM (rednote-hilab/dots.ocr, MIT) running on a separate
    vLLM+CUDA sidecar, so the worker gains ZERO new deps — this node is a pure httpx client. PDF-only:
    with no PDF view the base degrades to an empty IR (score 0), the correct behaviour for an
    escalation step. Tables arrive as HTML the mapper flattens into a grid; formulas as LaTeX; figures
    (Picture) as empty placeholders the figure_render stage crops from the normalized bbox.
    """

    KIND = "dots_ocr"
    NAME = "dots.ocr"
    SUMMARY = "Parse a PDF into the canonical IR with the dots.ocr per-element layout VLM sidecar."
    HOW_IT_WORKS = (
        "POSTs the PDF bytes to the dots.ocr sidecar, which renders each page to an image and sends "
        "it to the dots.ocr layout VLM (rednote-hilab/dots.ocr, served by vLLM on its own torch+CUDA "
        "runtime, GPU-only). The sidecar returns one reading-ordered block list per page — the model's "
        "per-element categories normalized to labels, tables as HTML, formulas as LaTeX already "
        "inlined, bboxes divided by the rendered page-image dims. The node maps that into the "
        "DocumentIR (top-left origin, no y-flip; tables flattened to a grid; Picture left as an empty "
        "crop placeholder). The sidecar's VLM is heavy, slow and built lazily: wire this as an "
        "OFF-by-default score_below escalation head after standard docling."
    )
    Config = ParserDotsOcrConfig
    UNIQUE_IN_GRAPH = True
    # The sidecar renders pages itself and is PDF-only: with no PDF view the base degrades to an empty
    # IR (score 0), which is the correct behaviour for an escalation step.
    NATIVE_FORMATS = frozenset()

    async def preflight(self) -> None:
        """Verify the sidecar is reachable and its token accepted, before any spend.

        Probes the sidecar's ``/health`` route — any answer (even non-200) proves the host is up; a
        401/403 surfaces a rejected bearer token. The VLM model is built lazily on the first /parse
        request, so /health is up well before the model loads.
        """
        config: ParserDotsOcrConfig = self.config
        await EndpointReachability.check(
            node_kind=self.KIND,
            base_url=config.base_url,
            api_key=config.api_key,
            timeout_seconds=config.preflight_timeout_seconds,
            path="/health",
        )

    async def _parse(self, source: IntakeResult) -> DocumentIR:
        """POST the PDF bytes to the sidecar and map its response into the canonical IR.

        Args:
            source (IntakeResult): The intake result carrying the PDF-view bytes to parse.

        Returns:
            DocumentIR: The IR mapped from the sidecar's per-page block contract.
        """
        config: ParserDotsOcrConfig = self.config
        # 1. Build headers — the raw PDF bytes ride in the body + the optional bearer token.
        headers = {"Content-Type": "application/pdf"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"

        async def _post(client: httpx.AsyncClient) -> dict:
            """One async call per document — raw PDF bytes in the body (the retryable operation)."""
            response = await client.post(
                "/parse",
                content=source.pdf_content,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

        # 2. The pooled client keeps the connection alive across retries (headers ride per-request)
        #    and self-heals a dead socket left by a sidecar restart; non-transient errors re-raise.
        payload = await NetworkRetry.run(
            lambda: HttpClientPool.run(
                _post, base_url=config.base_url, timeout=config.timeout_seconds
            ),
            max_retries=config.max_retries,
            retry_backoff_seconds=config.retry_backoff_seconds,
            label=f"parser '{self.KIND}'",
        )

        # 3. Map the sidecar's clean per-page block contract into the canonical IR.
        return DotsOcrIRMapper.map_response(
            payload, doc_id=source.source_hash, source_hash=source.source_hash
        )


__all__ = ["ParserDotsOcrNode"]
