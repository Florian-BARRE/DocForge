# ====== Code Summary ======
# BaseDoclingParserConfig — the config surface shared by every IN-WORKER Docling-family parser
# (standard docling + granite VLM). Both run their heavy, native convert in a KILLABLE subprocess the
# worker manages, so both carry the two caps that make an OOM / hang / crash a clean, attributed
# single-job failure instead of a wedged worker: a per-document TIME limit (the child is SIGKILLed
# past it), a RESIDENT-memory limit the worker's watchdog enforces (ON by default via the deployment's
# WORKER_PARSE_RSS_LIMIT_MB; the child is SIGKILLed past it, before the cgroup OOM-killer) and an
# opt-in address-space cap (RLIMIT_AS, off by default — it bounds virtual memory). The sidecar parsers (pp_structure, mineru…)
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
        "(which could otherwise reap the worker). 0 (default) means the deployment fallback "
        "(WORKER_PARSE_MEMORY_MB, off by default = no cap) — set a value to override it for this "
        "collection. It bounds VIRTUAL memory, which torch/onnx over-reserve (~5.7 GiB virtual for "
        "~2.3 GiB resident measured on a 6-page PDF), so size it >= 8192; note that on the "
        "GPU (granite) an RLIMIT_AS cap can break CUDA's large virtual reservations, so leave it 0 "
        "there and rely on the time cap + GPU-OOM kill + the resident-memory watchdog "
        "(parse_rss_limit_mb).",
    )
    parse_rss_limit_mb: int = Field(
        default=0,
        ge=0,
        description="Resident-memory (RSS) limit in MiB for the parse subprocess and any process it "
        "spawns, enforced by the worker's watchdog (sampled every 0.5 s): past it the child is "
        "SIGKILLed and the job fails with ParseMemoryExceededError naming the limit, before the "
        "container's OOM-killer could reap the worker. 0 (default) means the deployment default "
        "(WORKER_PARSE_RSS_LIMIT_MB — ON by default: 80% of the container/host memory minus a 1 GiB "
        "worker reserve). Unlike parse_memory_mb it counts only real resident memory, so it is safe "
        "on every parser including granite on the GPU. Raise it for a collection of heavy documents "
        "on a large worker; the warm child's loaded models (~1-2 GiB) count toward it.",
    )


__all__ = ["BaseDoclingParserConfig"]
