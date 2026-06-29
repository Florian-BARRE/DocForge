# ====== Code Summary ======
# EnrichRouting — the figure routing table, reproduced verbatim from the legacy FigureRoutingHelpers
# kind sets. Given a classified figure kind plus which capability chains are wired, it returns the
# single routing DECISION (decorative / OCR / VLM / chart-schema) that the classify step records on a
# FigureWork. Holding the decision in one pure helper keeps the routing table identical to the legacy
# per-figure path while the capabilities themselves are executed as separate per-figure passes.

# ====== Standard Library Imports ======
from __future__ import annotations

from dataclasses import dataclass

# ====== Internal Project Imports ======
from common_libs.domain.ir.models import FigureKind

# Figure kinds that trigger OCR routing (verbatim from the legacy FigureRoutingHelpers._OCR_KINDS).
_OCR_KINDS: frozenset[FigureKind] = frozenset(
    {FigureKind.SCANNED_TEXT, FigureKind.CHART, FigureKind.DIAGRAM}
)
# Figure kinds that trigger VLM routing (verbatim from the legacy FigureRoutingHelpers._VLM_KINDS).
_VLM_KINDS: frozenset[FigureKind] = frozenset(
    {FigureKind.CHART, FigureKind.DIAGRAM, FigureKind.PHOTO}
)


@dataclass(frozen=True)
class RoutingDecision:
    """
    Immutable per-figure routing decision taken once at classify time.

    Attributes:
        decorative (bool): The figure is DECORATIVE — skip all enrichment.
        do_ocr (bool): Run the OCR capability over the figure.
        do_vlm (bool): Run the VLM capability over the figure.
        use_chart_schema (bool): Request structured chart-to-data output from the VLM call.
    """

    decorative: bool
    do_ocr: bool
    do_vlm: bool
    use_chart_schema: bool


class EnrichRouting:
    """
    Static routing table mapping a figure kind + wired capabilities to a :class:`RoutingDecision`.

    Reproduces the legacy routing exactly: DECORATIVE -> skip; SCANNED_TEXT/CHART/DIAGRAM -> OCR;
    CHART/DIAGRAM/PHOTO -> VLM; CHART + chart_to_data -> structured chart-to-data. A capability is
    only ever routed when its chain is wired (``ocr_enabled`` / ``vlm_enabled``).
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        """Block instantiation — this is a static-only routing helper."""
        raise TypeError("EnrichRouting is a static-only class and cannot be instantiated.")

    @staticmethod
    def decide(
        kind: FigureKind,
        ocr_enabled: bool,
        vlm_enabled: bool,
        chart_to_data: bool,
    ) -> RoutingDecision:
        """
        Resolve the routing decision for one classified figure.

        Args:
            kind (FigureKind): The classified figure kind.
            ocr_enabled (bool): Whether an OCR chain is wired (None chain disables OCR entirely).
            vlm_enabled (bool): Whether a VLM chain is wired (None chain disables VLM entirely).
            chart_to_data (bool): The ``enrich.chart_to_data`` flag — only a CHART with this on
                requests the structured schema; otherwise a CHART is described like a normal figure.

        Returns:
            RoutingDecision: The per-figure decision (decorative / OCR / VLM / chart-schema).
        """
        # 1. DECORATIVE gates out of every capability (legacy returned early before OCR/VLM).
        decorative = kind == FigureKind.DECORATIVE

        # 2. OCR / VLM route only when both the chain is wired AND the kind warrants the capability.
        do_ocr = (not decorative) and ocr_enabled and (kind in _OCR_KINDS)
        do_vlm = (not decorative) and vlm_enabled and (kind in _VLM_KINDS)

        # 3. Chart-to-data is a parameter of the VLM call: only a CHART, only when the flag is on.
        use_chart_schema = (kind == FigureKind.CHART) and chart_to_data
        return RoutingDecision(
            decorative=decorative,
            do_ocr=do_ocr,
            do_vlm=do_vlm,
            use_chart_schema=use_chart_schema,
        )


__all__ = ["EnrichRouting", "RoutingDecision"]
