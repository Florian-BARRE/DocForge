# ====== Code Summary ======
# SidecarParserNode — the abstract base of every parser that is a NETWORK client of a model sidecar
# (dots_ocr, mineru, paddleocr_vl, pp_structure), not an in-process engine. It POSTs the PDF bytes to
# the sidecar's ENDPOINT (raw body, optional bearer, optional per-request query params), retries
# through the pooled client, and maps the sidecar's per-page block contract into the canonical IR via
# the engine's MAPPER. It inherits BaseParserNode's PDF-view resolution, empty-IR degradation, quality
# score and ScoredOutput, and implements the sidecar call + preflight (endpoint reachability) once. An
# engine subclass declares ONLY its registry KIND/NAME/docs, Config, ENDPOINT, MAPPER and
# ``_query_params`` (its sub-pipeline toggles, or None). Wire a sidecar parser as an OFF-by-default
# ScoreBelow escalation head after standard docling, never in the default/light blob: the sidecars
# are heavy, slow and optional (their model is built lazily sidecar-side).

# ====== Standard Library Imports ======
from abc import abstractmethod

# ====== Third-Party Library Imports ======
import httpx

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.http_pool import HttpClientPool
from shared_libs.pipelines.nodes.openai_compat import EndpointReachability
from shared_libs.pipelines.nodes.retry import NetworkRetry
from shared_libs.public_models import DocumentIR, IntakeResult

# ====== Local Project Imports ======
from ..base import BaseParserNode
from .config import SidecarParserConfig
from .mapper import SidecarIRMapper


class SidecarParserNode(BaseParserNode):
    """Abstract sidecar parser: the shared HTTP call + preflight; children declare their differences.

    PDF-only: the sidecar renders pages itself, so with no PDF view the base degrades to an empty IR
    (score 0), the correct behaviour for an escalation step. Registers nothing (no KIND).
    """

    Config = SidecarParserConfig
    UNIQUE_IN_GRAPH = True
    NATIVE_FORMATS = frozenset()

    # The sidecar route the PDF bytes are POSTed to (e.g. "/parse"). Set by each engine.
    ENDPOINT: str
    # The engine's response → IR adapter. Set by each engine.
    MAPPER: type[SidecarIRMapper]

    @abstractmethod
    def _query_params(self) -> dict[str, bool] | None:
        """The sub-pipeline toggles forwarded as query params, or None when the sidecar takes none."""
        ...

    async def preflight(self) -> None:
        """Verify the sidecar is reachable and its token accepted, before any spend.

        Probes the sidecar's ``/health`` route — any answer (even non-200) proves the host is up; a
        401/403 surfaces a rejected bearer token. The sidecar's model is built lazily on the first
        parse request, so /health is up well before the model loads.
        """
        config: SidecarParserConfig = self.config
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
        config: SidecarParserConfig = self.config
        # 1. Build the request — the raw PDF bytes ride in the body, the optional bearer token in the
        #    headers, and the enabled sub-pipelines (if the engine has any) as query params.
        headers = {"Content-Type": "application/pdf"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        request_kwargs: dict = {"content": source.pdf_content, "headers": headers}
        params = self._query_params()
        if params is not None:
            request_kwargs["params"] = params

        async def _post(client: httpx.AsyncClient) -> dict:
            """One async call per document — raw PDF bytes in the body (the retryable operation)."""
            response = await client.post(self.ENDPOINT, **request_kwargs)
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
        return self.MAPPER.map_response(
            payload, doc_id=source.source_hash, source_hash=source.source_hash
        )


__all__ = ["SidecarParserNode"]
