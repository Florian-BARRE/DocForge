# ====== Code Summary ======
# BaseDoclingParserConfig — the config surface shared by every IN-WORKER Docling-family parser
# (standard docling + granite VLM). Both run their heavy, native convert in a KILLABLE subprocess the
# worker manages, so both carry the two caps that make an OOM / hang / crash a clean, attributed
# single-job failure instead of a wedged worker: a per-document TIME budget (the child is SIGKILLed
# past it) and an optional address-space MEMORY budget (a runaway allocation dies with a clean
# MemoryError before the container's cgroup OOM-killer). The sidecar parsers (pp_structure, mineru…)
# are already out-of-process over HTTP and do NOT use this — they inherit TimeoutRetryConfig instead.

# ====== Third-Party Library Imports ======
from pydantic import Field

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import NodeConfig


class BaseDoclingParserConfig(NodeConfig):
    """Shared subprocess caps for the in-worker Docling-family parsers (docling + granite)."""

    parse_timeout_seconds: float = Field(
        default=600.0,
        gt=0,
        description="Wall-clock cap (s) for a SINGLE document's parse in the isolated subprocess. Past "
        "it the child is SIGKILLed and the job fails cleanly (attributed) — a hung native convert can "
        "never wedge the worker. Generous by default (docling on a hard scan can take minutes); lower "
        "it to fail heavy documents faster.",
    )
    parse_memory_mb: int = Field(
        default=0,
        ge=0,
        description="Address-space (RLIMIT_AS) cap in MiB for the parse subprocess. >0 makes a runaway "
        "allocation die with a clean, attributed MemoryError BEFORE the container's cgroup OOM-killer "
        "(which could otherwise reap the worker). 0 (default) disables the cap — the time budget + "
        "kill-on-crash still keep the worker alive. Tune ABOVE the model footprint; note that on the "
        "GPU (granite) an RLIMIT_AS cap can break CUDA's large virtual reservations, so leave it 0 "
        "there and rely on the time cap + GPU-OOM kill.",
    )


__all__ = ["BaseDoclingParserConfig"]
