# ====== Code Summary ======
# S012ParamHelpers — static extractors that turn each S0/S1/S2 stage instance into the
# fingerprint parameter dict consumed by compute_fingerprint().  Kept separate from the
# runner so the caching-interleaved stage methods stay focused on I/O orchestration.

# ====== Standard Library Imports ======
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from libs.pipeline.stages.s1_parse.core import S1ParseStage as _S1ParseStageType

# ====== Internal Project Imports ======
from libs.pipeline.stages.s0_ingest.core import S0IngestStage
from libs.pipeline.stages.s2_enrich import S2EnrichStage


class S012ParamHelpers:
    """
    Static helpers that extract fingerprint parameters from S0/S1/S2 stage instances.

    Each extractor returns the parameter dict feeding the node's blake3 fingerprint.
    Changing any returned value invalidates the cache for all documents.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("S012ParamHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def s0_params(s0: S0IngestStage) -> dict[str, Any]:
        """
        Extract S0 fingerprint parameters from the run's converter.

        Changing a converter parameter (name, version) invalidates the S0 cache
        for all documents.

        Args:
            s0 (S0IngestStage): The S0 ingest stage whose converter is inspected.

        Returns:
            dict[str, Any]: Fingerprint parameter dict (converter name and version).
        """
        return {
            "converter_name": getattr(s0._converter, "name", "gotenberg"),
            "converter_version": getattr(s0._converter, "version", "8"),
        }

    @staticmethod
    def s1_params(s1: _S1ParseStageType) -> dict[str, Any]:
        """
        Extract S1 fingerprint parameters from the run's parser.

        Changing parser name, version, or GPU mode invalidates S1 cache entries.
        The chain-aware fingerprint covers every provider in order so adding/removing/
        reordering parsers invalidates the cache as expected.

        Args:
            s1 (_S1ParseStageType): The S1 parse stage whose parser is inspected.

        Returns:
            dict[str, Any]: Fingerprint parameter dict (parse chain signature).
        """
        return {"parse_chain": s1._parse_chain.signature()}

    @staticmethod
    def s2_params(s2: S2EnrichStage) -> dict[str, Any]:
        """
        Extract S2 fingerprint parameters from the run's enrichment stage.

        Delegates to S2EnrichStage.params_for_fingerprint() which returns classifier
        name/version, OCR chain signature, VLM chain signature, and budget cap.

        Args:
            s2 (S2EnrichStage): The S2 enrichment stage.

        Returns:
            dict[str, Any]: Fingerprint parameter dict.
        """
        return s2.params_for_fingerprint()


# ------------------- Public API ------------------- #
__all__ = ["S012ParamHelpers"]
