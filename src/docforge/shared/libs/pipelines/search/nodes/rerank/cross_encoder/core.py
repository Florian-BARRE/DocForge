# ====== Code Summary ======
# RerankCrossEncoderNode — the real, selectable cross-encoder reranker. It sits between retrieve and
# hydrate (retrieve → rerank → hydrate): it re-SCORES the fused candidate pool with a stronger signal
# and hands the downstream hydrate node the SAME CandidateSet artefact it used to get from retrieve —
# so hydrate keeps doing the ranking + top_k cut, unchanged. The node is PURE: it reads passage text
# through the injected read port (never a store import) and makes ONE stateless /rerank HTTP call (the
# same category as the embed node's provider call); it writes nothing.
#
# Rule for the un-reranked tail (documented once, here): only the reranked top_n candidates are
# emitted. The cross-encoder judges the top_n candidates by fusion score; candidates past top_n are
# dropped — they ranked below the judged set and top_n is kept oversized vs the delivered top_k, so a
# dropped candidate could never have reached the final page. This is the simplest correct rule and
# avoids mixing incomparable score scales (cross-encoder [0, 1] vs raw fusion scores).

# ====== Standard Library Imports ======
import asyncio

# ====== Internal Project Imports ======
from shared_libs.pipelines.nodes.openai_compat import EndpointReachability
from shared_libs.pipelines.registry import NodeRegistry
from shared_libs.public_models.search import CandidateSet

# ====== Local Project Imports ======
from ...base import PortBackedNode
from .client import CrossEncoderRerankClient
from .config import RerankCrossEncoderConfig
from .io import RerankCrossEncoderConsumes, RerankCrossEncoderProduces

# The provenance stamped on every re-scored candidate (the retrieval branch that last touched it).
_RERANK_SOURCE = "cross_encoder"

# The degrade note stamped when the rerank call is given up on (slow/cold reranker) — the search
# still answers with the fusion-order candidates rather than sinking to the run cap (a 504).
_RERANK_DEGRADED = "rerank skipped — reranker busy, fusion-order results"


@NodeRegistry.register("rerank")
class RerankCrossEncoderNode(PortBackedNode):
    """Re-score the fused candidate pool with a cross-encoder reranker (query, passage pairs)."""

    KIND = "cross_encoder"
    NAME = "Cross-encoder rerank"
    SUMMARY = "Re-score the fused pool's top candidates with a cross-encoder reranker."
    HOW_IT_WORKS = (
        "Takes the top_n candidates of the fused pool (by fusion score), hydrates ONLY their passage "
        "text through the bound read port, then POSTs one (query, passages) batch to the reranker's "
        "TEI-compatible /rerank route. Each returned [0, 1] score overwrites its candidate's score by "
        "index; the re-scored candidates are emitted best-first as a plain CandidateSet the hydrate "
        "node consumes unchanged. Candidates past top_n are dropped (they ranked below the judged "
        "set). No store write — a pure port read + one provider call."
    )
    Config = RerankCrossEncoderConfig
    Consumes = RerankCrossEncoderConsumes
    Produces = RerankCrossEncoderProduces
    UNIQUE_IN_GRAPH = True

    async def preflight(self) -> None:
        """Verify the reranker endpoint is reachable and its token accepted, before any spend.

        Probes the TEI-compatible ``/health`` route — any answer (even non-200) proves the host is
        up; a 401/403 surfaces a rejected bearer token. Reads ``self.config`` only, so the app's
        on-demand health sweep can call it without wiring the read port.
        """
        config: RerankCrossEncoderConfig = self.config
        await EndpointReachability.check(
            node_kind=self.KIND,
            base_url=config.base_url,
            api_key=config.api_key,
            timeout_seconds=config.timeout_seconds,
            path="/health",
        )

    async def run(self, data: RerankCrossEncoderConsumes) -> RerankCrossEncoderProduces:
        """
        Re-score the fused candidate pool with the cross-encoder and emit it best-first.

        Args:
            data (RerankCrossEncoderConsumes): The fused candidate pool + the query spec.

        Returns:
            RerankCrossEncoderProduces: The re-scored pool (a CandidateSet) + its top-1 score.
        """
        config: RerankCrossEncoderConfig = self.config
        # Preserve any encode-degradation note across the rerank so delivery still surfaces it.
        degraded = data.candidates.degraded

        # 1. Take the top_n candidates by incoming fusion score — the cheap cross-encoder pass.
        pool = sorted(
            data.candidates.candidates, key=lambda candidate: candidate.score, reverse=True
        )[: config.top_n]
        if not pool:
            return RerankCrossEncoderProduces(
                candidates=CandidateSet(candidates=[], degraded=degraded), score=0.0
            )

        # 2. Hydrate ONLY the cut set's passage text through the injected read port (a vanished row
        #    is dropped here, so texts stays aligned with the candidates it is built from).
        hydrated = await self._read_port.hydrate([candidate.chunk_id for candidate in pool])
        judged = [candidate for candidate in pool if hydrated.get(candidate.chunk_id) is not None]
        texts = [hydrated[candidate.chunk_id].text or "" for candidate in judged]
        if not texts:
            return RerankCrossEncoderProduces(
                candidates=CandidateSet(candidates=[], degraded=degraded), score=0.0
            )

        # 3. One stateless provider call — cross-encoder scores in [0, 1], returned by input index.
        #    The call is bounded by a wall-clock cap (asyncio.wait_for) well below the run's 30 s cap:
        #    a cold reranker cold-loads for ~30 s on its first call, so without this the whole search
        #    would sit until the run cap (a 504). Instead the rerank is given up on (a catchable
        #    Exception — TimeoutError or a provider error) and the fusion-order candidates answer
        #    un-reranked. CancelledError (the run's own wall-clock cap) is NOT an Exception, so it
        #    still propagates through wait_for and becomes the runner's timeout path.
        client = CrossEncoderRerankClient(config.base_url, config.api_key, config.timeout_seconds)
        try:
            scores = await asyncio.wait_for(
                client.rerank(data.spec.text, texts, config.truncate),
                timeout=config.degrade_after_seconds,
            )
        except Exception as exc:
            self.logger.warning(
                f"Rerank degraded ({type(exc).__name__}: {exc}) — returning fusion-order candidates"
            )
            notes = [note for note in (degraded, _RERANK_DEGRADED) if note]
            return RerankCrossEncoderProduces(
                candidates=CandidateSet(candidates=judged, degraded="; ".join(notes)),
                score=judged[0].score,
            )

        # 4. Map each score onto its candidate by index; overwrite the score + provenance.
        score_by_index = dict(scores)
        if len(score_by_index) != len(texts):
            # The reranker returned fewer scores than passages sent — the unscored candidates are
            # silently dropped below. Surface the shortfall rather than let it pass unnoticed.
            self.logger.warning(
                f"Reranker '{config.model}' returned {len(score_by_index)} score(s) for "
                f"{len(texts)} passage(s) — {len(texts) - len(score_by_index)} candidate(s) dropped"
            )
        reranked = [
            candidate.model_copy(
                update={"score": score_by_index[position], "source": _RERANK_SOURCE}
            )
            for position, candidate in enumerate(judged)
            if position in score_by_index
        ]

        # 5. Emit the re-scored pool best-first; the aggregate score is the top-1 (a ScoreBelow gate).
        reranked.sort(key=lambda candidate: candidate.score, reverse=True)
        top_score = reranked[0].score if reranked else 0.0
        self.logger.debug(
            f"Reranked {len(reranked)}/{len(data.candidates.candidates)} candidate(s) "
            f"(model '{config.model}', top score {top_score:.4f})"
        )
        return RerankCrossEncoderProduces(
            candidates=CandidateSet(candidates=reranked, degraded=degraded), score=top_score
        )


__all__ = ["RerankCrossEncoderNode"]
