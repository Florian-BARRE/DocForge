# ====== Code Summary ======
# SidecarGeometry — the per-block provenance normalization shared by every sidecar parser. The
# sidecars return PIXEL bboxes with a TOP-LEFT origin (so there is NO y-flip, unlike docling) plus the
# rendered page-image dims; the only work is dividing by those dims, ordering the corners and clamping
# to [0, 1]. A malformed bbox or missing dims degrade to a full-page box so the block still lands on
# its page rather than being dropped.

# ====== Internal Project Imports ======
from shared_libs.public_models import Provenance


class SidecarGeometry:
    """Static bbox/provenance helpers for sidecar block contracts — pure, no side effects."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SidecarGeometry is a static-only class and cannot be instantiated.")

    @staticmethod
    def normalize_bbox(
        bbox: object, image_width: float, image_height: float
    ) -> tuple[float, float, float, float]:
        """
        Normalize a pixel bbox [x0, y0, x1, y1] to [0, 1] using the rendered page-image dims.

        Sidecar bboxes already use a TOP-LEFT origin, so there is no y-flip — the only work is
        dividing by the page-image dims. Missing/invalid bbox or dims degrade to a full-page box so
        the block still lands on its page rather than being dropped.

        Args:
            bbox (object): The block's ``bbox`` (expected [x0, y0, x1, y1] in pixels).
            image_width (float): Rendered page-image width in pixels (the x divisor).
            image_height (float): Rendered page-image height in pixels (the y divisor).

        Returns:
            tuple[float, float, float, float]: The normalized (x0, y0, x1, y1) clamped to [0, 1].
        """
        # 1. Guard the divisors: a zero/missing dim would blow up or mis-scale every crop.
        width = image_width if image_width and image_width > 0 else 1.0
        height = image_height if image_height and image_height > 0 else 1.0

        # 2. A malformed bbox degrades to the full page rather than dropping the block.
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return (0.0, 0.0, 1.0, 1.0)

        # 3. Divide by the page dims (top-left origin, no flip), order the corners, clamp to [0, 1].
        x0, y0, x1, y1 = (float(value) for value in bbox)
        x0, x1 = x0 / width, x1 / width
        y0, y1 = y0 / height, y1 / height
        x0, x1 = min(x0, x1), max(x0, x1)
        y0, y1 = min(y0, y1), max(y0, y1)

        def clamp(value: float) -> float:
            return max(0.0, min(1.0, value))

        return (clamp(x0), clamp(y0), clamp(x1), clamp(y1))

    @staticmethod
    def make_provenance(
        bbox: object, page_index: int, image_width: float, image_height: float
    ) -> Provenance:
        """Build a Provenance from a pixel bbox + the page index and rendered page-image dims."""
        return Provenance(
            page=page_index,
            bbox=SidecarGeometry.normalize_bbox(bbox, image_width, image_height),
        )


__all__ = ["SidecarGeometry"]
