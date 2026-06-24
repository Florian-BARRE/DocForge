# ====== Code Summary ======
# ImageFactory — synthesizes small PNG images (charts, diagrams, photos, logos) entirely
# in memory with Pillow, so corpus builders can embed real raster figures without shipping
# binary assets. Each kind is visually distinct so the figure-classifier (if ever enabled)
# has plausible signal; for the default structure-only suite they simply guarantee the
# pipeline produces FIGURE blocks and figure crops.

# ====== Standard Library Imports ======
from __future__ import annotations

import io
import math

# ====== Third-Party Library Imports ======
from PIL import Image, ImageDraw


class ImageFactory:
    """Static factory of synthetic PNG images used to embed figures in corpus documents."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ImageFactory is a static-only class and cannot be instantiated.")

    @classmethod
    def bar_chart(cls, title: str = "Revenue", width: int = 640, height: int = 400) -> bytes:
        """
        Render a labelled bar chart (a CHART-kind figure).

        Args:
            title (str): Caption drawn at the top of the chart.
            width (int): Image width in pixels.
            height (int): Image height in pixels.

        Returns:
            bytes: PNG-encoded image.
        """
        # 1. White canvas with a titled header
        img = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(img)
        draw.text((16, 12), f"Figure - {title}", fill="black")

        # 2. Draw five bars of varying height with axis lines
        values = [0.35, 0.62, 0.48, 0.91, 0.27]
        base_y, left_x, bar_w, gap = height - 40, 60, 70, 40
        draw.line([(left_x, 40), (left_x, base_y)], fill="black", width=2)
        draw.line([(left_x, base_y), (width - 20, base_y)], fill="black", width=2)
        for i, v in enumerate(values):
            x0 = left_x + 16 + i * (bar_w + gap)
            top = base_y - int(v * (base_y - 60))
            draw.rectangle([x0, top, x0 + bar_w, base_y], fill=(60, 90 + i * 25, 200))

        # 3. Encode to PNG bytes
        return cls._encode(img)

    @classmethod
    def diagram(cls, width: int = 640, height: int = 380) -> bytes:
        """
        Render a boxes-and-arrows flow diagram (a DIAGRAM-kind figure).

        Returns:
            bytes: PNG-encoded image.
        """
        # 1. Canvas with three connected boxes
        img = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(img)
        boxes = [(40, 150, 200, 230), (260, 150, 420, 230), (480, 150, 600, 230)]
        labels = ["Ingest", "Enrich", "Index"]
        for (x0, y0, x1, y1), label in zip(boxes, labels):
            draw.rectangle([x0, y0, x1, y1], outline="black", width=3)
            draw.text((x0 + 16, y0 + 28), label, fill="black")

        # 2. Connect the boxes with arrow stems
        for (x0, _, x1, _), (nx0, _, _, _) in zip(boxes, boxes[1:]):
            draw.line([(x1, 190), (nx0, 190)], fill=(200, 40, 40), width=3)

        # 3. Encode to PNG bytes
        return cls._encode(img)

    @classmethod
    def photo(cls, width: int = 560, height: int = 360) -> bytes:
        """
        Render a smooth colour-gradient stand-in for a photograph (a PHOTO-kind figure).

        Returns:
            bytes: PNG-encoded image.
        """
        # 1. Per-pixel radial gradient — visually "photographic", no flat regions
        img = Image.new("RGB", (width, height))
        cx, cy = width / 2, height / 2
        max_d = math.hypot(cx, cy)
        px = img.load()
        for y in range(height):
            for x in range(width):
                d = math.hypot(x - cx, y - cy) / max_d
                px[x, y] = (int(40 + 180 * d), int(120 * (1 - d)), int(200 * d))

        # 2. Encode to PNG bytes
        return cls._encode(img)

    @classmethod
    def logo(cls, width: int = 160, height: int = 80) -> bytes:
        """
        Render a tiny banner/logo (a DECORATIVE-kind figure, normally skipped by enrichment).

        Returns:
            bytes: PNG-encoded image.
        """
        # 1. Solid band with a couple of accent circles
        img = Image.new("RGB", (width, height), (24, 28, 48))
        draw = ImageDraw.Draw(img)
        draw.ellipse([10, 20, 50, 60], fill=(99, 102, 241))
        draw.ellipse([40, 20, 80, 60], fill=(56, 189, 248))
        draw.text((92, 34), "DF", fill="white")

        # 2. Encode to PNG bytes
        return cls._encode(img)

    @staticmethod
    def _encode(img: Image.Image) -> bytes:
        """Encode a Pillow image to PNG bytes without touching the filesystem."""
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
