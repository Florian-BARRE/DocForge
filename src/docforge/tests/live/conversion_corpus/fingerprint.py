# ====== Code Summary ======
# Turns one ingested document (raw API artefacts) into a stable, human-diffable fingerprint:
#   * document facts       — format, pages, language, title, status, chunk count, warning, hashes
#   * IR                   — block/table/figure counts, structure / text / geometry / table hashes
#   * chunks               — count, per-chunk token count + text hash + block ordinals, and an
#                            aggregate boundary hash (the silent search risk when a chunking
#                            dependency changes)
#   * markdown             — length + hash of the generated view
#   * trace                — the node kinds the run went through
#   * api shapes           — the type skeleton of each response (a field/type change shows up)
# Every volatile value (UUIDs, timestamps, durations) is dropped or replaced by an ordinal.

# ====== Standard Library Imports ======
import hashlib
import json
import re
from typing import Any

# ====== Local Project Imports ======
from .ingestor import IngestedDocument

DOCUMENT_FACT_FIELDS = (
    "format",
    "mime_type",
    "file_size",
    "page_count",
    "language",
    "title",
    "display_title",
    "source_kind",
    "status",
    "source_hash",
    "pipeline_version",
    "enabled",
    "chunk_count",
    "warning_reason",
    "failure_reason",
    "searchable",
    "metadata",
)
JOB_FIELDS = ("status", "kind", "progress", "current_stage", "attempt", "error", "error_type")
BBOX_DECIMALS = 3
SHAPE_LIST_SAMPLE = 1


def _sha(value: Any) -> str:
    """Short sha256 of a JSON-canonical value."""
    text = (
        value if isinstance(value, str) else json.dumps(value, sort_keys=True, ensure_ascii=False)
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


_HEX_DIGEST = re.compile(r"^[0-9a-f]{16,64}$")


def mark_digests(value: Any) -> Any:
    """Prefixes every bare hex digest with ``sha:``.

    The snapshot is full of content hashes; a bare hex string trips the repository's secret
    scanners (high-entropy hex), the prefix keeps them readable and unflagged.
    """
    if isinstance(value, dict):
        return {key: mark_digests(item) for key, item in value.items()}
    if isinstance(value, list):
        return [mark_digests(item) for item in value]
    if isinstance(value, str) and _HEX_DIGEST.match(value):
        return f"sha:{value}"
    return value


def _pdf_blob_kind(document: dict[str, Any]) -> str | None:
    blob = document.get("pdf_blob_hash")
    if blob is None:
        return None
    return "source" if blob == document.get("source_hash") else "converted"


class ShapeSkeleton:
    """The type skeleton of a JSON response: every key with its type, a list by its first item."""

    @classmethod
    def of(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: cls.of(value[key]) for key in sorted(value)}
        if isinstance(value, list):
            return [cls.of(item) for item in value[:SHAPE_LIST_SAMPLE]]
        return type(value).__name__


class IrFingerprint:
    """Fingerprints the canonical IR with block ids replaced by reading-order ordinals."""

    def __init__(self, ir: dict[str, Any]) -> None:
        self._ir = ir
        self._ordinal = {block["id"]: index for index, block in enumerate(ir.get("blocks", []))}

    def _ord(self, block_id: str | None) -> int | None:
        return None if block_id is None else self._ordinal.get(block_id, -1)

    def build(self) -> dict[str, Any]:
        blocks = self._ir.get("blocks", [])
        tables = self._ir.get("tables", [])
        figures = self._ir.get("figures", [])
        by_type: dict[str, int] = {}
        for block in blocks:
            by_type[block["block_type"]] = by_type.get(block["block_type"], 0) + 1
        structure = [
            [
                b["block_type"],
                b["page"],
                b["reading_order"],
                b.get("level"),
                self._ord(b.get("parent_id")),
                b.get("is_boilerplate"),
                b.get("language"),
            ]
            for b in blocks
        ]
        geometry = [[round(v, BBOX_DECIMALS) for v in (b.get("bbox") or [])] for b in blocks]
        return {
            "keys": sorted(self._ir),
            "blocks": len(blocks),
            "blocks_by_type": dict(sorted(by_type.items())),
            "tables": len(tables),
            "figures": len(figures),
            "enrichments": len(self._ir.get("enrichments", [])),
            "structure_hash": _sha(structure),
            "text_hash": _sha([b.get("text") for b in blocks]),
            "geometry_hash": _sha(geometry),
            "tables_hash": _sha(
                [
                    [
                        self._ord(t.get("block_id")),
                        t["n_rows"],
                        t["n_cols"],
                        t["has_header"],
                        t["cells"],
                        t.get("linearized_md"),
                    ]
                    for t in tables
                ]
            ),
            "figure_crop_hashes": [f.get("crop_blob_hash") for f in figures],
        }


class ChunkFingerprint:
    """Fingerprints the chunk list: count, per-chunk size/text hash/blocks and the boundary hash."""

    def __init__(self, chunks: list[dict[str, Any]], ordinal: dict[str, int]) -> None:
        self._chunks = chunks
        self._ordinal = ordinal

    def build(self) -> dict[str, Any]:
        per_chunk = [
            {
                "index": chunk["chunk_index"],
                "tokens": chunk["token_count"],
                "chars": len(chunk["text"]),
                "text_sha": _sha(chunk["text"]),
                "blocks": [self._ordinal.get(b, -1) for b in chunk.get("block_ids", [])],
                "page_number": chunk.get("page_number"),
                "role": chunk.get("role"),
                "strategy": chunk.get("strategy"),
                "heading_path": chunk.get("heading_path"),
                "metadata": chunk.get("metadata"),
            }
            for chunk in self._chunks
        ]
        return {
            "count": len(per_chunk),
            "total_tokens": sum(c["tokens"] for c in per_chunk),
            "boundary_hash": _sha(
                [[c["index"], c["tokens"], c["blocks"], c["text_sha"]] for c in per_chunk]
            ),
            "chunks": per_chunk,
        }


class DocumentFingerprinter:
    """Builds the full fingerprint of an :class:`IngestedDocument`."""

    def fingerprint(self, ingested: IngestedDocument) -> dict[str, Any]:
        ir = IrFingerprint(ingested.ir)
        events = ingested.trace.get("events", [])
        return mark_digests(
            {
                "document": {
                    **{name: ingested.document.get(name) for name in DOCUMENT_FACT_FIELDS},
                    # A converted PDF (Gotenberg) embeds timestamps, so its hash is run-volatile: only
                    # record whether the canonical PDF is the original upload itself.
                    "pdf_blob": _pdf_blob_kind(ingested.document),
                },
                "job": {name: ingested.job.get(name) for name in JOB_FIELDS},
                "ir": ir.build(),
                "chunks": ChunkFingerprint(ingested.chunks, ir._ordinal).build(),
                "markdown": {"chars": len(ingested.markdown), "sha": _sha(ingested.markdown)},
                "trace": sorted({f"{e['node_kind']}:{e['status']}" for e in events}),
                "shapes": {
                    "document": ShapeSkeleton.of(ingested.document),
                    "chunks": ShapeSkeleton.of(ingested.chunks),
                    "ir": ShapeSkeleton.of(ingested.ir),
                    "job": ShapeSkeleton.of(ingested.job),
                    "trace_event": ShapeSkeleton.of(events),
                },
            }
        )
