# ====== Code Summary ======
# Stateless helpers for the SeaweedFS S3-compatible object store.
# Provides content-addressed key builders and botocore configuration utilities.
# All methods are static or class-level — no aioboto3 session required.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus


# Object-store key conventions (content-addressed layout):
#   originals/{sha256}                              — original file bytes
#   derived/{sha256}/pdf                            — original→PDF conversion
#   derived/{sha256}/pages/{n}.png                  — page render PNG (0-indexed)
#   derived/{sha256}/figures/{block_id}.png         — figure crop PNG
#   derived/{sha256}/{s0_fp}/s0_meta.json           — S0 stage output metadata (P2 node cache)
#   derived/{sha256}/{s1_fp}/ir.json                — serialized DocumentIR JSON (pre-enrichment)
#   derived/{sha256}/{s1_fp}/s1_meta.json           — S1 stage output metadata (P2 node cache)
#   derived/{sha256}/{s1_fp}/doc.md                 — faithful markdown view
#   derived/{sha256}/{s2_fp}/ir_enriched.json       — enriched DocumentIR JSON (P3)
#   derived/{sha256}/{s2_fp}/s2_meta.json           — S2 stage output metadata (P3 node cache)


class S3Helpers:
    """
    Stateless helpers for S3-compatible object store operations.

    Provides content-addressed key builders (one per artifact type) and the
    botocore path-style addressing configuration required by SeaweedFS.

    All methods are static — this class is never instantiated.
    """

    logger = loggerplusplus.bind(identifier="S3Helpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Prevent instantiation — this is a static-only utility class."""
        raise TypeError("S3Helpers is a static-only class and cannot be instantiated.")

    # ─── Key builders (content-addressed layout) ──────────────────────────────

    @staticmethod
    def key_original(source_hash: str) -> str:
        """Key for the original uploaded file."""
        return f"originals/{source_hash}"

    @staticmethod
    def key_pdf(source_hash: str) -> str:
        """Key for the original→PDF conversion artefact."""
        return f"derived/{source_hash}/pdf"

    @staticmethod
    def key_figure_crop(source_hash: str, block_id: str) -> str:
        """Key for a figure crop PNG (legacy, per-block layout).

        Docling block IDs use '#/pictures/N' format. The '#' character causes
        presigned-URL signature mismatches with SeaweedFS (boto3 encodes it as '%23'
        in the URL but the SigV2 canonical path differs). We strip '#' and replace
        '/' with '_' so the resulting S3 key only contains URL-safe characters.

        Kept for backward compatibility with IR rows persisted before content-
        addressed crops were introduced.  New uploads use
        :meth:`key_figure_crop_by_hash` so a repeating logo / page header lands
        in a single PNG shared across every block (and every document) that
        contains the same pixels.
        """
        safe_id = block_id.replace("#", "").replace("/", "_").strip("_")
        return f"derived/{source_hash}/figures/{safe_id}.png"

    @staticmethod
    def key_figure_crop_by_hash(crop_hash: str) -> str:
        """Content-addressed key for a figure crop PNG.

        ``crop_hash`` is ``sha256(crop_bytes).hexdigest()`` — identical pixel
        bytes yield identical keys, so a logo that repeats across every slide of
        a deck (or every document of a collection) is stored as a single PNG.
        The 2-char prefix avoids piling 100k objects into one S3 "directory".
        """
        return f"figures/by-hash/{crop_hash[:2]}/{crop_hash}.png"

    @staticmethod
    def key_ir(source_hash: str, parse_fp: str) -> str:
        """Key for the serialized DocumentIR JSON."""
        return f"derived/{source_hash}/{parse_fp}/ir.json"

    @staticmethod
    def key_markdown(source_hash: str, serialize_fp: str) -> str:
        """Key for the faithful markdown view."""
        return f"derived/{source_hash}/{serialize_fp}/doc.md"

    @staticmethod
    def key_s0_meta(source_hash: str, s0_fp: str) -> str:
        """Key for the S0 stage output meta JSON (P2 node cache reference)."""
        return f"derived/{source_hash}/{s0_fp}/s0_meta.json"

    @staticmethod
    def key_s1_meta(source_hash: str, s1_fp: str) -> str:
        """Key for the S1 stage output meta JSON (P2 node cache reference)."""
        return f"derived/{source_hash}/{s1_fp}/s1_meta.json"

    @staticmethod
    def key_ir_enriched(source_hash: str, s2_fp: str) -> str:
        """Key for the enriched DocumentIR JSON (P3 — after S2 OCR/VLM enrichment)."""
        return f"derived/{source_hash}/{s2_fp}/ir_enriched.json"

    @staticmethod
    def key_s2_meta(source_hash: str, s2_fp: str) -> str:
        """Key for the S2 stage output meta JSON (P3 node cache reference)."""
        return f"derived/{source_hash}/{s2_fp}/s2_meta.json"

    # ─── Botocore configuration ───────────────────────────────────────────────

    @classmethod
    def boto_path_style_config(cls):
        """
        Return a botocore Config enforcing path-style addressing.

        SeaweedFS does not support virtual-hosted-style (e.g. bucket.host:8333).
        Path-style (host:8333/bucket/key) is required.

        Returns:
            botocore.config.Config: Configured botocore Config object.
        """
        from botocore.config import Config

        cls.logger.debug(f"Building botocore path-style config for SeaweedFS compatibility.")
        return Config(s3={"addressing_style": "path"})
