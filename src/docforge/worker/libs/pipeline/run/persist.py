# ====== Code Summary ======
# IngestPersistHelpers — the Postgres side-effects of the ingest lifecycle, ported from the legacy
# s012_persist + trace_flush and retargeted to the new node-engine stage outputs. It owns: building
# the document's implicit_meta (file-intrinsic + IR-derived stats + S3 refs + fingerprints + chain
# lineage), persisting the IR blocks and flipping the document to the intermediate 'parsed' status
# after the enrich stage, flushing the embed-chain traces after embed/index, and the terminal
# 'done' / 'failed' document transitions. Pure I/O helper over the injected IngestInfra.

# ====== Standard Library Imports ======
import uuid
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Internal Project Imports ======
from common_libs.pipelines.core.ingest.stages.enrich.result import EnrichResult
from common_libs.pipelines.core.ingest.stages.ingest.io import IngestStageIngestOutput
from common_libs.pipelines.core.ingest.stages.parse.result import ParseResult
from common_libs.storage.s3.helpers import S3Helpers

# ====== Local Project Imports ======
from .deps import IngestInfra


class IngestPersistHelpers:
    """
    Static helper for the document-lifecycle Postgres writes of the ingest run.

    Every method takes the frozen ``IngestInfra`` bundle so the hooks stay free of repeated infra
    keyword arguments. The terminal 'done' status is written only after the whole pipeline succeeds.
    """

    logger = loggerplusplus.bind(identifier="IngestPersist")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("IngestPersistHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def build_implicit_meta(
        ingest_output: IngestStageIngestOutput,
        ir: Any,
        parse_result: ParseResult,
        ingest_fp: str,
        parse_fp: str,
        ir_key: str,
        enrich_result: EnrichResult | None,
        enrich_fp: str | None,
    ) -> dict[str, Any]:
        """
        Assemble the document's implicit_meta from the ingest / parse / enrich artefacts.

        Args:
            ingest_output (IngestStageIngestOutput): The ingest stage output (file-intrinsic meta).
            ir (DocumentIR): The final IR (enriched when enrich ran).
            parse_result (ParseResult): The parse artefact (markdown key).
            ingest_fp (str): Ingest stage fingerprint.
            parse_fp (str): Parse stage fingerprint.
            ir_key (str): S3 key of the (pre-enrichment) IR JSON.
            enrich_result (EnrichResult | None): The enrich stage output, or None when skipped.
            enrich_fp (str | None): Enrich stage fingerprint, or None.

        Returns:
            dict: The implicit_meta dict written to the document record.
        """
        # 1. File-intrinsic layer + IR-derived counts + S3 refs + parse lineage.
        meta: dict[str, Any] = {
            **ingest_output.implicit_meta,
            "n_blocks": len(ir.blocks),
            "n_figures": len(ir.figure_blocks),
            "n_tables": len(ir.table_blocks),
            "s0_fingerprint": ingest_fp,
            "s1_fingerprint": parse_fp,
            "ir_key": ir_key,
            "markdown_key": parse_result.markdown_key,
            "chain_traces": [t.model_dump() for t in ir.chain_traces],
            "quality_score": ir.quality_score,
        }

        # 2. Enrichment layer (counters + provider-cache hits) when the enrich stage ran.
        if enrich_result is not None and enrich_fp is not None:
            meta["s2_fingerprint"] = enrich_fp
            meta["figures_enriched"] = enrich_result.figures_processed
            meta["ocr_calls"] = enrich_result.ocr_calls
            meta["vlm_calls"] = enrich_result.vlm_calls
            meta["chart_extractions"] = enrich_result.chart_extractions
            meta["ocr_cache_hits"] = enrich_result.ocr_cache_hits
            meta["vlm_cache_hits"] = enrich_result.vlm_cache_hits
            meta["classifier_calls"] = enrich_result.classifier_calls
            meta["classifier_cache_hits"] = enrich_result.classifier_cache_hits
        return meta

    @classmethod
    async def persist_after_enrich(
        cls,
        infra: IngestInfra,
        doc_id: uuid.UUID,
        source_hash: str,
        ingest_output: IngestStageIngestOutput,
        parse_result: ParseResult,
        ir: Any,
        ingest_fp: str,
        parse_fp: str,
        enrich_result: EnrichResult | None,
        enrich_fp: str | None,
        parse_cache_hit: bool,
        enrich_cache_hit: bool,
    ) -> None:
        """
        Persist the IR blocks and flip the document to the intermediate 'parsed' status.

        Block insertion is skipped when both parse and enrich were cache hits (the blocks already
        exist from the first run). 'parsed' is intermediate; the terminal 'done' is written only after
        the whole pipeline (chunk / embed / index) succeeds.

        Args:
            infra (IngestInfra): The worker infra bundle.
            doc_id (uuid.UUID): The document id.
            source_hash (str): Content address (drives the IR S3 key).
            ingest_output (IngestStageIngestOutput): The ingest stage output.
            parse_result (ParseResult): The parse artefact.
            ir (DocumentIR): The final (enriched) IR whose blocks are persisted.
            ingest_fp (str): Ingest stage fingerprint.
            parse_fp (str): Parse stage fingerprint.
            enrich_result (EnrichResult | None): The enrich stage output, or None when skipped.
            enrich_fp (str | None): Enrich stage fingerprint, or None.
            parse_cache_hit (bool): Whether the parse stage was a cache hit.
            enrich_cache_hit (bool): Whether the enrich stage was a cache hit.
        """
        # 1. Blocks already exist when both parse and enrich were served from cache.
        blocks_already_in_db = parse_cache_hit and (enrich_result is None or enrich_cache_hit)
        async with infra.postgres.session() as session:
            if not blocks_already_in_db:
                await infra.block_repo.bulk_insert(
                    session=session, document_id=doc_id, blocks=ir.blocks
                )
            await infra.document_repo.update_status(
                session,
                doc_id,
                "parsed",
                page_count=ir.n_pages,
                language=ir.language,
                implicit_meta=cls.build_implicit_meta(
                    ingest_output=ingest_output,
                    ir=ir,
                    parse_result=parse_result,
                    ingest_fp=ingest_fp,
                    parse_fp=parse_fp,
                    ir_key=S3Helpers.key_ir(source_hash, parse_fp),
                    enrich_result=enrich_result,
                    enrich_fp=enrich_fp,
                ),
            )

    @classmethod
    async def flush_embed_traces(
        cls, infra: IngestInfra, doc_id: uuid.UUID, embed_result: Any
    ) -> None:
        """
        Append the embed-chain traces onto the document's implicit_meta (indexing lineage).

        Args:
            infra (IngestInfra): The worker infra bundle.
            doc_id (uuid.UUID): The document id.
            embed_result (IngestStageEmbedIndexResult | None): The embed/index stage output.
        """
        # 1. Nothing to flush when embed/index did not run or produced no traces.
        if embed_result is None or not embed_result.chain_traces:
            return
        async with infra.postgres.session() as session:
            current = await infra.document_repo.get_by_id(session, doc_id)
            if current is None:
                return
            patched = dict(current.implicit_meta or {})
            patched["embed_chain_traces"] = [t.model_dump() for t in embed_result.chain_traces]
            await infra.document_repo.update_status(
                session, doc_id, current.status, implicit_meta=patched
            )

    @staticmethod
    async def mark_done(infra: IngestInfra, doc_id: uuid.UUID) -> None:
        """Flip the document to the terminal 'done' status (whole pipeline succeeded)."""
        async with infra.postgres.session() as session:
            await infra.document_repo.update_status(session, doc_id, "done")

    @classmethod
    async def mark_failed(cls, infra: IngestInfra, doc_id: uuid.UUID) -> None:
        """Flip the document to 'failed', tolerating a secondary DB error (never masks the cause)."""
        try:
            async with infra.postgres.session() as session:
                await infra.document_repo.update_status(session, doc_id, "failed")
        except Exception as exc:  # never mask the original stage error — but log this one loudly
            cls.logger.error(f"Failed to mark document {doc_id} as 'failed': {exc}")


__all__ = ["IngestPersistHelpers"]
