# ====== Code Summary ======
# ProviderRegistry — resolves a declarative PipelineConfig into concrete pipeline stages
# (spec §6: locality → provider → device), and describes each stage's tunable parameters and
# selectable providers so the UI generates itself (GET /playground/stages).
#
# Every provider is a ProviderSpec (id + params).  Params supplied in the request (e.g. a
# Mistral API key typed into the playground) take precedence over deployment env defaults —
# this is what lets a user wire an external provider on the fly.  Availability checks are
# cheap (package import, file presence, TCP reachability) and credential-aware.

# ====== Standard Library Imports ======
from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

# ====== Third-Party Library Imports ======
from loggerplusplus import LoggerClass
from pydantic import BaseModel

# ====== Internal Project Imports ======
from pipeline.pipeline_config import (
    ChunkConfig,
    EnrichConfig,
    PipelineConfig,
    ProviderSpec,
    SplitMethodConfig,
    _is_secret_key,
)
from pipeline.provider_cache import ProviderCallCache
from pipeline.stages.chunking import (
    SectionSplitter,
    SemanticParams,
)
from pipeline.stages.s2_enrich import S2EnrichStage
from pipeline.stages.s4_chunk import S4ChunkStage
from pipeline.stages.s5_contextualize import S5ContextualizeStage
from providers.chain import ProviderChain
from providers.classifier.local.layout_labels import LayoutLabelsClassifier
from providers.classifier.local.vit_onnx import VitOnnxConfig, VitOnnxClassifier
from providers.ocr.local.paddle_ocr import PaddleOcrConfig
from providers.ocr.external.mistral_ocr import MistralOcrConfig
from providers.parser.local.docling import DoclingBackend, DoclingConfig
from providers.vlm.local.openai_compat import LocalVlmConfig
from providers.vlm.external.openai_compat import OpenAIVlmConfig
from storage.s3.client import S3Client


class ProviderUnavailableError(Exception):
    """
    Raised when a PipelineConfig requests a provider that cannot run in this deployment.

    Mapped to HTTP 422 by the router with an actionable message.

    Attributes:
        capability (str): Capability that failed to resolve (e.g. "ocr", "parse").
        provider (str): Requested provider/backend id.
        reason (str): Why it is unavailable.
    """

    def __init__(self, capability: str, provider: str, reason: str) -> None:
        self.capability = capability
        self.provider = provider
        self.reason = reason
        super().__init__(f"{capability}:{provider} unavailable — {reason}")


@dataclass(slots=True)
class ResolvedStages:
    """
    Concrete pipeline stages resolved from a PipelineConfig for a single run.

    S0/S6 are handled outside this struct (S0 is constant; S6 owns a live Qdrant connection
    managed by the worker/app, not the registry).

    Attributes:
        parser (DoclingBackend): The resolved S1 parser backend.
        s2 (S2EnrichStage): Enrichment stage — always present (pipeline is fixed S0→S6).
        s4 (S4ChunkStage): Chunking stage — always present.
        s5 (S5ContextualizeStage): Contextualization stage — always present.
    """

    parser: DoclingBackend
    s2: S2EnrichStage
    s4: S4ChunkStage
    s5: S5ContextualizeStage


class ProviderRegistry(LoggerClass):
    """
    Resolves PipelineConfig → instantiated stages, and describes the configurable surface.

    Shared infrastructure (S3, provider cache) and deployment credential/endpoint defaults
    come from construction; per-run provider choices + params come from the PipelineConfig.
    """

    def __init__(
        self,
        s3: S3Client,
        provider_cache: ProviderCallCache,
        runtime_config: Any,
    ) -> None:
        """
        Initialize the registry with shared infrastructure and deployment defaults.

        Args:
            s3 (S3Client): Object store client (figure crops live here).
            provider_cache (ProviderCallCache): Cross-document provider-call cache.
            runtime_config (Any): RUNTIME_CONFIG — fallback credentials/endpoints used when
                a ProviderSpec omits a param, plus the basis for availability checks.
        """
        LoggerClass.__init__(self)
        self._s3 = s3
        self._provider_cache = provider_cache
        self._cfg = runtime_config

    # ─── Stage schema (drives the self-building UI) ─────────────────────────────

    @staticmethod
    def _params_from_instance(instance: Any) -> list[dict]:
        """
        Build the UI param schema list from a pre-filled Config instance.

        Uses the JSON schema for field types and the instance values for defaults,
        masking secrets.  Excludes the 'id' discriminator field.

        Args:
            instance (Any): A Config BaseModel instance with deployment defaults merged.

        Returns:
            list[dict]: Param descriptors for the playground UI.
        """
        from pipeline.pipeline_config import _is_secret_key
        schema = instance.__class__.model_json_schema()
        result = []
        for name, field_schema in schema.get("properties", {}).items():
            if name == "id":
                continue
            value = getattr(instance, name, None)
            is_secret = _is_secret_key(name)
            ftype = field_schema.get("type", "string")
            ui_type = (
                "secret" if is_secret
                else "bool" if ftype == "boolean"
                else "float" if ftype == "number"
                else "int" if ftype == "integer"
                else "str"
            )
            result.append({
                "key": name,
                "label": field_schema.get("description", name.replace("_", " ").title()),
                "type": ui_type,
                "default": ("•••" if is_secret and value else value),
                "note": "",
            })
        return result

    def _auto_providers(self, category: str, kind: str = "single") -> list[dict]:
        """
        Build the stage group descriptor for a provider category using the auto-registry.

        Iterates all registered Config classes for the category, calls availability()
        and merge_defaults() on each to derive the full provider descriptor with
        deployment-specific defaults pre-filled.

        Args:
            category (str): Provider registry category key (e.g. "ocr", "vlm").
            kind (str): "single", "multi", or "optional" — passed to the UI group.

        Returns:
            list[dict]: Provider descriptors ready for the stage group's "providers" list.
        """
        from providers._registry import get_configs
        providers = []
        for config_cls in get_configs(category).values():
            available, note = config_cls.availability(self._cfg)
            instance = config_cls().merge_defaults(self._cfg)
            providers.append({
                "id": config_cls.model_fields["id"].default,
                "label": getattr(config_cls, "_label", config_cls.__name__),
                "available": available,
                "selectable": True,
                "note": note,
                "params": self._params_from_instance(instance),
            })
        return providers

    def describe_stages(self) -> dict[str, Any]:
        """
        Describe every pipeline stage: its tunable params and selectable providers.

        Fully auto-derived from the provider registry — no hardcoded provider IDs.
        Adding a new provider auto-appears here the next time this method is called.

        Returns:
            dict: {"stages": [StageSchema, ...]} — each stage lists its groups and providers.
        """
        # Trigger auto-import for all categories so @register decorators fire.
        from providers._registry import auto_import
        for pkg in (
            "providers.converter",
            "providers.parser",
            "providers.classifier",
            "providers.ocr",
            "providers.vlm",
            "providers.embed",
        ):
            auto_import(pkg)
        # split_method configs live in params.py, imported via chunking __init__
        import pipeline.stages.chunking as _chunking_pkg  # noqa: F401

        return {
            "stages": [
                {
                    "id": "s0", "label": "S0 · INGEST", "name": "INGEST",
                    "description": "blake3 fingerprint + SHA-256 dedup + S3 upload.",
                    "params": [], "groups": [],
                },
                {
                    "id": "s1", "label": "S1 · PARSE", "name": "PARSE",
                    "description": "Convert + parse the document into the canonical IR block tree.",
                    "params": [],
                    "groups": [
                        {"key": "parse.provider", "kind": "single", "capability": "parse",
                         "label": "Parser backend",
                         "providers": self._auto_providers("parser", "single")},
                    ],
                },
                {
                    "id": "s2", "label": "S2 · ENRICH", "name": "ENRICH",
                    "description": "Classify figures, then route to OCR / VLM / chart-to-data.",
                    "params": [
                        {"key": "enrich.chart_to_data", "label": "Chart → data", "type": "bool",
                         "default": False, "note": "Extract chart series into a structured table"},
                        {"key": "enrich.max_budget_usd", "label": "Max budget (USD)", "type": "float",
                         "default": 0.0, "note": "Per-job spend cap; 0 = no limit"},
                    ],
                    "groups": [
                        {"key": "enrich.classifier", "kind": "single", "capability": "classifier",
                         "label": "Figure classifier",
                         "providers": self._auto_providers("classifier", "single")},
                        {"key": "enrich.ocr_chain", "kind": "multi", "capability": "ocr",
                         "label": "OCR chain (escalation order)",
                         "providers": self._auto_providers("ocr", "multi")},
                        {"key": "enrich.vlm", "kind": "optional", "capability": "vlm",
                         "label": "VLM (grounded description)",
                         "providers": self._auto_providers("vlm", "optional")},
                    ],
                },
                {
                    "id": "s4", "label": "S4 · CHUNK", "name": "CHUNK",
                    "description": "Structure-aware chunking: heading skeleton + configurable intra-section split.",
                    "params": [
                        {"key": "chunk.reinject_breadcrumb", "label": "Reinject breadcrumb", "type": "bool",
                         "default": True, "note": "Prepend section path to embed_text"},
                        {"key": "chunk.merge_short_sections", "label": "Merge short sections", "type": "bool",
                         "default": True, "note": "Fold heading-only / tiny sections into neighbours"},
                        {"key": "chunk.hierarchical", "label": "Hierarchical chunks", "type": "bool",
                         "default": False, "note": "Emit a parent chunk per section over its children"},
                        {"key": "chunk.cross_references", "label": "Cross-references", "type": "bool",
                         "default": True, "note": "Detect see Figure/Article links between chunks"},
                    ],
                    "groups": [
                        {"key": "chunk.split_method", "kind": "single", "capability": "split_method",
                         "label": "Intra-section split method",
                         "providers": self._auto_providers("split_method", "single")},
                    ],
                },
                {
                    "id": "s5", "label": "S5 · CONTEXTUALIZE", "name": "CONTEXTUALIZE",
                    "description": "Inject section titles and position metadata into each chunk.",
                    "params": [], "groups": [],
                },
                {
                    "id": "s6", "label": "S6 · EMBED", "name": "EMBED",
                    "description": "Embed chunks and upsert multi-vector points into Qdrant.",
                    "params": [],
                    "groups": [
                        {"key": "embed.provider", "kind": "single", "capability": "embed",
                         "label": "Embedding provider",
                         "providers": self._auto_providers("embed", "single")},
                    ],
                },
            ]
        }

    # ─── Availability probes ────────────────────────────────────────────────────

    def _endpoint_reachable(self, base_url: str) -> bool:
        """
        Parse host/port from a URL and TCP-probe it.

        Args:
            base_url (str): HTTP/HTTPS base URL to probe.

        Returns:
            bool: True when the TCP connection succeeds within the probe timeout.
        """
        # 1. Guard against empty or unconfigured URLs before parsing
        if not base_url:
            return False
        parsed = urlparse(base_url)
        host = parsed.hostname
        if not host:
            return False
        # 2. Fall back to the scheme's default port when none is explicit
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return self._tcp_reachable(host, port)

    @staticmethod
    def _tcp_reachable(host: str, port: int, timeout: float = 1.0) -> bool:
        """
        Attempt a short TCP connect and return True if the socket opens within the timeout.

        Args:
            host (str): Target hostname or IP address.
            port (int): Target TCP port.
            timeout (float): Connect timeout in seconds (default 1.0).

        Returns:
            bool: True when the connection succeeds; False on any error.
        """
        try:
            with socket.create_connection((host, int(port)), timeout=timeout):
                return True
        except Exception:
            return False

    # ─── Stage resolution ──────────────────────────────────────────────────────

    def build_stages(self, config: PipelineConfig) -> ResolvedStages:
        """
        Resolve a PipelineConfig into concrete pipeline stages.

        Validates each requested provider against availability (credential-aware) and raises
        ProviderUnavailableError (→ HTTP 422) when a knob cannot be honored.

        Args:
            config (PipelineConfig): The per-run pipeline configuration.

        Returns:
            ResolvedStages: Parser + S2/S4/S5 stages — always all present (S6 is owned by
                the caller's infra as it holds a live Qdrant connection).

        Raises:
            ProviderUnavailableError: When a requested provider cannot run here.
        """
        parser = self._build_parser(config.parse.provider)
        s2 = self._build_s2(config.enrich)
        s4 = self._build_chunk_stage(config.chunk)
        s5 = S5ContextualizeStage()

        return ResolvedStages(parser=parser, s2=s2, s4=s4, s5=s5)

    def _build_chunk_stage(self, chunk: ChunkConfig) -> S4ChunkStage:
        """
        Build the S4 chunking stage from config: split method + atomic policy + mode.

        Args:
            chunk (ChunkConfig): The chunking configuration block.

        Returns:
            S4ChunkStage: Wired chunking stage.

        Raises:
            ProviderUnavailableError: When the semantic method is requested but TEI is unreachable.
        """
        # 1. Resolve the intra-section split method (the decision-tree-by-method)
        splitter = self._build_splitter(chunk.split_method)

        # 2. Wire the heading skeleton + atomic policy + mode around it
        return S4ChunkStage(
            splitter=splitter,
            heading_rules=chunk.heading_rules,
            reinject_breadcrumb=chunk.reinject_breadcrumb,
            merge_short_sections=chunk.merge_short_sections,
            atomic=chunk.atomic,
            cross_references=chunk.cross_references,
            hierarchical=chunk.hierarchical,
        )

    def _build_splitter(self, spec: SplitMethodConfig) -> SectionSplitter:
        """
        Instantiate the requested intra-section split method from its typed config.

        Merges deployment defaults into the typed config then delegates to build().
        Semantic split requires a reachable TEI endpoint and is checked before build().

        Args:
            spec (SplitMethodConfig): Typed split method config (discriminated union).

        Returns:
            SectionSplitter: Wired splitter.

        Raises:
            ProviderUnavailableError: When semantic is requested but TEI is unreachable.
        """
        # 1. Merge deployment defaults into the typed config (e.g. TEI_BASE_URL for semantic)
        merged = spec.merge_defaults(self._cfg)

        # 2. Semantic split requires a reachable TEI embedding endpoint — check before build()
        if isinstance(merged, SemanticParams):
            base_url = merged.base_url or self._cfg.TEI_BASE_URL
            if not self._endpoint_reachable(base_url):
                raise ProviderUnavailableError(
                    "chunk_strategy", "semantic",
                    f"Semantic chunking needs a reachable TEI endpoint (got {base_url!r}).",
                )

        # 3. Delegate instantiation to the typed config (build() knows its own splitter)
        return merged.build()

    def build_enrich_and_chunk_stages(
        self,
        config: "PipelineConfig",
    ) -> tuple["S2EnrichStage", "S4ChunkStage", "S5ContextualizeStage"]:
        """
        Build S2, S4, S5 from a typed PipelineConfig — for the startup default stack.

        Called by entrypoint.py and worker.py to replace the 9 direct provider
        instantiations with a single config-driven call.  S6 is built per-job by
        StageEngine._build_s6_from_config() and is excluded here.

        Args:
            config (PipelineConfig): Fully typed pipeline config (from build_default_pipeline).

        Returns:
            tuple: (S2EnrichStage, S4ChunkStage, S5ContextualizeStage) ready to inject.
        """
        # 1. Build S2 components from config
        classifier = self._build_classifier(config.enrich.classifier)
        ocr_chain = self._build_ocr_chain(config.enrich.ocr_chain) if config.enrich.ocr_chain else None
        vlm_chain = self._build_vlm_chain(config.enrich.vlm) if config.enrich.vlm is not None else None

        s2 = S2EnrichStage(
            classifier=classifier,
            ocr_chain=ocr_chain,
            vlm_chain=vlm_chain,
            s3=self._s3,
            provider_cache=self._provider_cache,
            max_budget_usd=config.enrich.max_budget_usd,
        )

        # 2. Build S4 splitter from config
        splitter = self._build_splitter(config.chunk.split_method)
        s4 = S4ChunkStage(splitter=splitter)

        # 3. S5 has no config
        s5 = S5ContextualizeStage()

        return s2, s4, s5

    def _build_parser(self, spec: ProviderSpec) -> DoclingBackend:
        """
        Instantiate the requested parser backend, or reject if unavailable.

        Args:
            spec (ProviderSpec): Parser provider specification (typed ParserConfig union).

        Returns:
            DoclingBackend: Instantiated parser backend.

        Raises:
            ProviderUnavailableError: When the requested parser is not installed.
        """
        # 1. Docling is the only installed backend — reject anything else early
        if isinstance(spec, DoclingConfig):
            merged = spec.merge_defaults(self._cfg)
            return merged.build()
        raise ProviderUnavailableError(
            "parse", getattr(spec, "id", str(spec)),
            "Only the Docling backend is installed in this deployment."
        )

    def _build_s2(self, enrich: EnrichConfig) -> S2EnrichStage:
        """
        Build the S2 enrichment stage from config.

        Args:
            enrich (EnrichConfig): Enrichment configuration block.

        Returns:
            S2EnrichStage: Wired enrichment stage (always built — pipeline is fixed S0→S6).
        """
        # 1. Instantiate classifier, OCR chain, and VLM chain from their individual specs
        classifier = self._build_classifier(enrich.classifier)
        ocr_chain = self._build_ocr_chain(enrich.ocr_chain)
        vlm_chain = self._build_vlm_chain(enrich.vlm)

        # 3. Wire all sub-providers into the S2 stage
        return S2EnrichStage(
            classifier=classifier,
            ocr_chain=ocr_chain,
            vlm_chain=vlm_chain,
            s3=self._s3,
            provider_cache=self._provider_cache,
            max_budget_usd=enrich.max_budget_usd,
        )

    def _build_classifier(self, spec: ProviderSpec) -> LayoutLabelsClassifier | VitOnnxClassifier:
        """
        Build the figure classifier from its typed config.

        Args:
            spec (ProviderSpec): Classifier provider specification (typed ClassifierConfig union).

        Returns:
            LayoutLabelsClassifier | VitOnnxClassifier: Instantiated classifier.

        Raises:
            ProviderUnavailableError: When the ONNX model file is missing.
        """
        # 1. ViT ONNX classifier — merge env defaults (model_path, use_gpu) then check model file
        if isinstance(spec, VitOnnxConfig):
            merged = spec.merge_defaults(self._cfg)
            if not os.path.exists(merged.model_path):
                raise ProviderUnavailableError(
                    "classifier", "vit_onnx", f"ONNX model not found at {merged.model_path}."
                )
            return merged.build()
        # 2. Default: zero-cost heuristic classifier — merge_defaults is a no-op, build() suffices
        merged = spec.merge_defaults(self._cfg)
        return merged.build()

    def _build_ocr_chain(self, specs: list[ProviderSpec]) -> ProviderChain | None:
        """
        Build an OCR escalation chain from provider specs (params over env defaults).

        Credentials supplied in the spec take precedence over deployment environment defaults,
        allowing the playground to wire an external provider without env changes.

        Args:
            specs (list[ProviderSpec]): OCR provider specs in escalation order.

        Returns:
            ProviderChain | None: Wired OCR chain, or None when specs is empty.

        Raises:
            ProviderUnavailableError: When a provider is unavailable or misconfigured.
        """
        # 1. No OCR providers configured → S2 will skip OCR routing entirely
        if not specs:
            return None

        # 2. Instantiate each provider in escalation order
        built = []
        for spec in specs:
            merged = spec.merge_defaults(self._cfg)
            if isinstance(merged, PaddleOcrConfig):
                # Local package — cannot run without the paddleocr import
                try:
                    import paddleocr  # noqa: F401
                except Exception:
                    raise ProviderUnavailableError(
                        "ocr", "paddle_ocr", "paddleocr package is not installed."
                    )
            elif isinstance(merged, MistralOcrConfig):
                # External API — api_key required (merge_defaults pulled env default already)
                if not merged.api_key:
                    raise ProviderUnavailableError(
                        "ocr", "mistral_ocr",
                        "No API key — fill it in the playground or set MISTRAL_OCR_API_KEY.",
                    )
            else:
                raise ProviderUnavailableError("ocr", getattr(merged, "id", str(merged)), "Unknown OCR provider id.")
            built.append(merged.build())

        # 3. Wrap the ordered list in a chain that escalates on low confidence
        return ProviderChain(
            providers=built,
            escalate_if=lambda r: r.confidence < self._cfg.OCR_CONFIDENCE_THRESHOLD,
        )

    def _build_vlm_chain(self, spec: ProviderSpec | None) -> ProviderChain | None:
        """
        Build a single-provider VLM chain from its spec (params over env defaults).

        Args:
            spec (ProviderSpec | None): VLM provider spec, or None to skip VLM routing.

        Returns:
            ProviderChain | None: Wired VLM chain (single provider, no escalation), or None.

        Raises:
            ProviderUnavailableError: When the provider id is unknown or base URL is missing.
        """
        # 1. VLM is optional — None means the stage will not attempt VLM grounding
        if spec is None:
            return None

        # 2. Merge deployment defaults into the typed config then check availability
        merged = spec.merge_defaults(self._cfg)

        if isinstance(merged, LocalVlmConfig):
            # Local server (vLLM, Ollama, LM Studio) — no auth required; base_url must be set
            if not merged.base_url:
                raise ProviderUnavailableError("vlm", "openai_compat", "No VLM base URL configured.")
        elif isinstance(merged, OpenAIVlmConfig):
            # External cloud API — both base_url and api_key are required
            if not merged.base_url:
                raise ProviderUnavailableError("vlm", "openai", "No VLM base URL configured.")
            if not merged.api_key:
                raise ProviderUnavailableError(
                    "vlm", "openai",
                    "No API key — fill it in the playground or set VLM_API_KEY.",
                )
        else:
            raise ProviderUnavailableError(
                "vlm", getattr(merged, "id", str(merged)),
                "Unknown VLM provider id. Valid ids: 'openai_compat' (local server), 'openai' (cloud API)."
            )

        # 3. Wrap in a non-escalating chain (VLM is always the terminal provider)
        return ProviderChain(providers=[merged.build()], escalate_if=lambda r: False)


# ─── Model-driven schema derivation (single source of truth = the Pydantic params models) ──────

# JSON-Schema scalar type → UI param type understood by the configurator.
_JSON_TYPE_TO_UI: dict[str, str] = {"integer": "int", "number": "float", "boolean": "bool", "string": "str"}


def _params_from_model(model: type[BaseModel]) -> list[dict[str, Any]]:
    """
    Derive UI param descriptors from a Pydantic model's JSON schema (no hand-maintained list).

    Types, defaults, bounds (ge/le → minimum/maximum) and descriptions all come straight from the
    model, so the discovery schema can never drift from what the code actually accepts.

    Args:
        model (type[BaseModel]): A params model (e.g. SemanticParams).

    Returns:
        list[dict[str, Any]]: Param descriptors in the configurator's shape.
    """
    schema = model.model_json_schema()
    out: list[dict[str, Any]] = []
    for name, prop in schema.get("properties", {}).items():
        ui_type = _JSON_TYPE_TO_UI.get(prop.get("type", "string"), "str")
        if ui_type == "str" and _is_secret_key(name):
            ui_type = "secret"
        desc = _param(name, ui_type, prop.get("title", name), prop.get("default"), prop.get("description", ""))
        if "minimum" in prop:
            desc["min"] = prop["minimum"]
        if "maximum" in prop:
            desc["max"] = prop["maximum"]
        out.append(desc)
    return out


# ─── Param-schema helpers (keep describe_stages() declarative) ──────────────────

def _param(name: str, ptype: str, label: str, default: Any, desc: str, **extra: Any) -> dict[str, Any]:
    """
    Build a single parameter descriptor for the stage schema.

    Args:
        name (str): Dot-path key (e.g. ``"enrich.chart_to_data"``).
        ptype (str): Parameter type tag understood by the UI (``"bool"``, ``"int"``, etc.).
        label (str): Human-readable label shown in the configurator.
        default (Any): Default value pre-filled in the UI.
        desc (str): Short description shown as a tooltip.
        **extra (Any): Additional fields merged into the descriptor (e.g. ``min``, ``max``).

    Returns:
        dict[str, Any]: Parameter descriptor dict.
    """
    return {"name": name, "type": ptype, "label": label, "default": default, "description": desc, **extra}


def _rules(name: str, label: str, default: list[dict[str, Any]], desc: str) -> dict[str, Any]:
    """
    Build a list-of-(level, pattern) heading-rule editor parameter descriptor.

    Args:
        name (str): Dot-path key.
        label (str): Human-readable label.
        default (list[dict[str, Any]]): Default heading rules.
        desc (str): Tooltip description.

    Returns:
        dict[str, Any]: Parameter descriptor.
    """
    return _param(name, "rules", label, default, desc)
