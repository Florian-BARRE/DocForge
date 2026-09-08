# ====== Code Summary ======
# The Qwen2-VL `smart_resize` algorithm — PURE and offline-testable. dots.ocr is a Qwen2-VL-family VLM
# whose image processor resizes every input to dims that are a multiple of `factor` (28) and whose pixel
# count fits within [min_pixels, max_pixels], BEFORE the vision encoder. The model therefore returns
# bounding boxes in that RESIZED frame, not in the frame we rendered. To keep the bbox normalization
# divisor honest, the sidecar resizes each page to exactly these dims itself and reports them as the
# page's image_width/image_height, and pins the same min/max on the transformers processor so it does not
# re-resize differently. Isolating this here (no PIL/torch/transformers import) makes it deterministic and
# unit-testable on this CPU-only VM.

# ====== Standard Library Imports ======
import math


class SmartResize:
    """Static-only Qwen2-VL smart-resize dim computation — never instantiated."""

    def __new__(cls, *args: object, **kwargs: object) -> "SmartResize":
        raise TypeError("SmartResize is a static-only class and cannot be instantiated.")

    @staticmethod
    def dims(
        height: int, width: int, factor: int, min_pixels: int, max_pixels: int
    ) -> tuple[int, int]:
        """
        Compute the Qwen2-VL smart-resized (height, width) for an input image.

        Rounds each side to the nearest multiple of ``factor``, then scales the whole image down (if the
        rounded area exceeds ``max_pixels``) or up (if it is below ``min_pixels``) so the final area
        fits the budget while each side stays a multiple of ``factor`` and at least ``factor``.

        Args:
            height (int): Source image height in pixels (must be > 0).
            width (int): Source image width in pixels (must be > 0).
            factor (int): The dimension granularity (28 for Qwen2-VL).
            min_pixels (int): Lower bound on the resized pixel count.
            max_pixels (int): Upper bound on the resized pixel count.

        Returns:
            tuple[int, int]: The resized (height, width), each a positive multiple of ``factor``.
        """
        # 1. Round each side to the nearest multiple of `factor`, never below one `factor`.
        h_bar = max(factor, round(height / factor) * factor)
        w_bar = max(factor, round(width / factor) * factor)

        # 2. If the rounded box overflows the pixel budget, scale it DOWN (floor keeps it under max).
        if h_bar * w_bar > max_pixels:
            beta = math.sqrt((height * width) / max_pixels)
            h_bar = max(factor, math.floor(height / beta / factor) * factor)
            w_bar = max(factor, math.floor(width / beta / factor) * factor)
        # 3. If it underflows, scale it UP (ceil keeps it over min).
        elif h_bar * w_bar < min_pixels:
            beta = math.sqrt(min_pixels / (height * width))
            h_bar = math.ceil(height * beta / factor) * factor
            w_bar = math.ceil(width * beta / factor) * factor

        return h_bar, w_bar


__all__ = ["SmartResize"]
