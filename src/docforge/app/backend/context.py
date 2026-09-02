# ====== Code Summary ======
# Typed service locator for DocForge. All shared services are accessed via CONTEXT —
# never imported directly in route files. Values are assigned in entrypoint.py at startup.

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerPlusPlus

# ====== Internal Project Imports ======
from config import RUNTIME_CONFIG
from shared_libs.pipelines.build import PipelineBuilder
from shared_libs.pipelines.edit import GraphEditor
from shared_libs.pipelines.ingest.stages import StageCompiler
from shared_libs.pipelines.validation import GraphValidator
from shared_libs.services.db import Database

# ====== Local Project Imports ======
from .libs.estimate import CostEstimateService
from .libs.health import CollectionHealthService
from .libs.metrics import MetricsService
from .libs.search import SearchService
from .utils.queue import QueueClient


class CONTEXT:
    """
    Shared application context — typed service locator.

    Type annotations only. All values are assigned at startup in entrypoint.py.
    Access via CONTEXT.<attribute> anywhere in the codebase.
    Never instantiate this class.
    """

    # ── Core infrastructure ──────────────────────────────────────────────────
    logger: LoggerPlusPlus
    RUNTIME_CONFIG: type[RUNTIME_CONFIG]

    # ── Pipeline design surface ──────────────────────────────────────────────
    pipeline_builder: PipelineBuilder
    graph_validator: GraphValidator
    graph_editor: GraphEditor
    stage_compiler: StageCompiler

    # ── Stores + queue (admission writes and status reads — execution is the worker's) ──
    database: Database
    queue: QueueClient

    # ── Search execution (the graph-based search pipeline runs INLINE in the request) ──
    # The /collections/{id}/search endpoint is NOT cut over to this yet; it is the invocation
    # seam for the search graph (a later phase wires it to a route).
    search_service: SearchService

    # ── Collection health (on-demand, zero-spend reachability + build probe) ──
    # Backs GET /collections/{id}/health — builds both graphs, sweeps their providers, rolls up.
    health_service: CollectionHealthService

    # ── Cost estimate (on-demand, zero-spend pre-hoc token/$/volume preview of an ingestion) ──
    # Backs POST /collections/{id}/estimate — reads config + cheap doc stats, runs the pure estimator.
    estimate_service: CostEstimateService

    # ── Metrics (Prometheus /metrics — infra-gauge refresh + exposition rendering) ──
    # Backs GET /metrics; the HTTP request series are fed passively by HttpMetricsMiddleware.
    metrics_service: MetricsService
