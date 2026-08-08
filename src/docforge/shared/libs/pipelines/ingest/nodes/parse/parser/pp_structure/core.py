# ====== Code Summary ======
# The PP-StructureV3 (PaddleOCR) parser node — a NETWORK client, not an in-process engine. It POSTs
# the PDF bytes to a sidecar (src/paddle_server) that runs the PaddleX layout-parsing pipeline on its
# own PaddlePaddle runtime, and maps the sidecar's clean per-page block contract into the canonical
# IR via PpStructureIRMapper. Subclasses BaseParserNode directly (no docling engine): it inherits the
# PDF-view resolution, empty-IR degradation, quality score and ScoredOutput, and implements ONLY
# _parse (async network I/O) plus preflight (endpoint reachability). Wire it as an OFF-by-default
# ScoreBelow escalation head after standard docling, never in the default/light blob — the sidecar is
# heavy and optional.

# ====== Third-Party Library Imports ======
import httpx

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.openai_compat import EndpointReachability
from shared_libs.pipelines.nodes.retry import NetworkRetry
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models import DocumentIR, IntakeResult

# ====== Local Project Imports ======
from ..base import BaseParserNode
from .config import ParserPpStructureConfig
from .mapper import PpStructureIRMapper


@NodeRegistry.register("parser")
class ParserPpStructureNode(BaseParserNode):
    """
    Parse a PDF with the PP-StructureV3 sidecar, mapping its layout-parsing output to the canonical IR.

    A SOTA layout parser (Apache-2.0) running on a separate PaddlePaddle sidecar, so the worker gains
    ZERO new deps — this node is a pure httpx client. PDF-only: with no PDF view the base degrades to
    an empty IR (score 0), the correct behaviour for an escalation step. Tables arrive as HTML the
    mapper flattens into a grid; formulas as LaTeX; figures as empty placeholders the figure_render
    stage crops from the normalized bbox.
    """

    KIND = "pp_structure"
    NAME = "PP-StructureV3 (PaddleOCR)"
    SUMMARY = "Parse a PDF into the canonical IR with the PP-StructureV3 sidecar (PaddleOCR)."
    HOW_IT_WORKS = (
        "POSTs the PDF bytes to the PP-StructureV3 sidecar (a PaddleX layout-parsing pipeline on its "
        "own PaddlePaddle runtime), which returns one reading-ordered block list per page with tables "
        "as HTML and formulas as LaTeX already inlined. The node maps that into the DocumentIR — "
        "pixel bboxes normalized against the rendered page dims (top-left origin, no y-flip), tables "
        "flattened to a grid, figures left as empty crop placeholders. The sidecar is heavy and "
        "optional: wire this as an OFF-by-default score_below escalation head after standard docling."
    )
    Config = ParserPpStructureConfig
    UNIQUE_IN_GRAPH = True
    # The sidecar renders pages itself and is PDF-only: with no PDF view the base degrades to an empty
    # IR (score 0), which is the correct behaviour for an escalation step.
    NATIVE_FORMATS = frozenset()

    async def preflight(self) -> None:
        """Verify the sidecar is reachable and its token accepted, before any spend.

        Probes the sidecar's ``/health`` route — any answer (even non-200) proves the host is up; a
        401/403 surfaces a rejected bearer token.
        """
        config: ParserPpStructureConfig = self.config
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
        config: ParserPpStructureConfig = self.config
        # 1. Forward the enabled sub-pipelines as query params + the optional bearer token.
        params = {
            "use_table_recognition": config.use_table_recognition,
            "use_formula_recognition": config.use_formula_recognition,
            "use_seal_recognition": config.use_seal_recognition,
            "use_doc_orientation_classify": config.use_doc_orientation_classify,
            "use_doc_unwarping": config.use_doc_unwarping,
        }
        headers = {"Content-Type": "application/pdf"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"

        async def _post() -> dict:
            """One async call per document — raw PDF bytes in the body (the retryable operation)."""
            async with httpx.AsyncClient(
                base_url=config.base_url, timeout=config.timeout_seconds
            ) as client:
                response = await client.post(
                    "/layout-parsing",
                    content=source.pdf_content,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
            return response.json()

        # 2. Run the call under the shared bounded retry; a non-transient error re-raises at once.
        payload = await NetworkRetry.run(
            _post,
            max_retries=config.max_retries,
            retry_backoff_seconds=config.retry_backoff_seconds,
            label=f"parser '{self.KIND}'",
        )

        # 3. Map the sidecar's clean per-page block contract into the canonical IR.
        return PpStructureIRMapper.map_response(
            payload, doc_id=source.source_hash, source_hash=source.source_hash
        )


__all__ = ["ParserPpStructureNode"]
