# ====== Code Summary ======
# ViT ONNX figure classifier — loads a small Vision Transformer model from an ONNX file.
# Provides higher accuracy than LayoutLabelsClassifier when a trained model is available.
# Falls back to PHOTO (confidence 0.5) gracefully if the model file is absent.

from __future__ import annotations

import io
from typing import Any

from loggerplusplus import LoggerClass

from common_libs.providers.classifier.base import ClassificationResult, FigureClassifier
from common_libs.providers.model_cache import ModelCache
from common_libs.domain.ir.models import FigureKind

# Expected mapping from ONNX output class index → FigureKind.
# Must match the label order used during model training.
_CLASS_INDEX_MAP: dict[int, FigureKind] = {
    0: FigureKind.SCANNED_TEXT,
    1: FigureKind.CHART,
    2: FigureKind.DIAGRAM,
    3: FigureKind.PHOTO,
    4: FigureKind.DECORATIVE,
}

# Input resolution expected by the ViT model (224×224, standard ViT-B/16 convention)
_INPUT_SIZE: int = 224

# ImageNet normalization (used for ImageNet-pretrained ViT models)
_IMAGENET_MEAN: tuple[float, float, float] = (0.485, 0.456, 0.406)
_IMAGENET_STD: tuple[float, float, float] = (0.229, 0.224, 0.225)


class VitOnnxClassifier(FigureClassifier, LoggerClass):
    """
    Figure classifier backed by a small ViT (Vision Transformer) ONNX model.

    Config id: "vit_onnx"

    The model takes a 224×224 RGB image and outputs 5-class softmax probabilities
    corresponding to the five FigureKind values.  Inference runs via ONNX Runtime
    on CPU (or GPU when use_gpu=True and ONNXRuntime-GPU is installed).

    If the model file is absent or loading fails, the classifier silently degrades to
    returning PHOTO with confidence 0.5 — enrichment continues without hard failure.
    """

    name: str = "vit_onnx"
    version: str = "1.0"

    def __init__(self, model_path: str, use_gpu: bool = False) -> None:
        """
        Initialize the ViT ONNX classifier.

        Args:
            model_path (str): Filesystem path to the ``.onnx`` model file.
            use_gpu (bool): If True, use ONNX Runtime GPU (CUDA) execution provider.
        """
        LoggerClass.__init__(self)
        self._model_path = model_path
        self._use_gpu = use_gpu
        # The ONNX session is shared process-wide via ModelCache, keyed by the model-
        # determining params (path + device) so a new instance per job reuses the loaded model.
        self._model_key: tuple[str, str, bool] = ("vit_onnx.session", model_path, use_gpu)

    async def classify(
        self,
        img_bytes: bytes,
        label_hint: str | None = None,
    ) -> ClassificationResult:
        """
        Classify a figure image using the ViT ONNX model.

        Args:
            img_bytes (bytes): PNG or JPEG image bytes.
            label_hint (str | None): Ignored — ViT uses only visual features.

        Returns:
            ClassificationResult: Predicted FigureKind with softmax confidence.
        """
        import asyncio

        # 1. Run in thread pool — ONNX Runtime inference is CPU-bound
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._infer_sync, img_bytes)

    def _infer_sync(self, img_bytes: bytes) -> ClassificationResult:
        """
        Synchronous ONNX inference (runs inside a thread pool).

        Raises on any model-load/inference failure so the classifier chain can record the
        failed attempt and ESCALATE to the next classifier.  The terminal "all classifiers
        failed" case is handled upstream: the chain returns None and FigureEnricher applies
        its documented PHOTO fallback — but a single provider must not pre-empt escalation by
        fabricating that fallback itself.

        Raises:
            Exception: Re-raised on any ONNX import/load/inference failure.
        """
        try:
            import numpy as np  # type: ignore
            from PIL import Image  # type: ignore

            # 1. Resolve the process-shared ONNX Runtime session (loaded once via ModelCache).
            # ort.InferenceSession.run() is thread-safe, so concurrent inference on the shared
            # session needs no lock — only the one-time load is serialized inside ModelCache.
            session = ModelCache.get_or_load(self._model_key, self._build_session)

            # 2. Preprocess: resize → normalize → (1, 3, H, W) float32
            img = (
                Image.open(io.BytesIO(img_bytes))
                .convert("RGB")
                .resize((_INPUT_SIZE, _INPUT_SIZE), Image.BILINEAR)
            )
            arr = np.array(img, dtype=np.float32) / 255.0
            mean = np.array(_IMAGENET_MEAN, dtype=np.float32)
            std = np.array(_IMAGENET_STD, dtype=np.float32)
            arr = (arr - mean) / std
            arr = arr.transpose(2, 0, 1)[np.newaxis, :]  # (1, C, H, W)

            # 3. Run inference
            input_name = session.get_inputs()[0].name
            logits = session.run(None, {input_name: arr})[0][0]

            # 4. Softmax → argmax
            exp_l = np.exp(logits - logits.max())
            probs = exp_l / exp_l.sum()
            class_idx = int(probs.argmax())
            confidence = float(probs[class_idx])
            kind = _CLASS_INDEX_MAP.get(class_idx, FigureKind.PHOTO)

            self.logger.debug(
                f"VitOnnxClassifier: class={kind} confidence={confidence:.3f}"
            )
            return ClassificationResult(kind=kind, confidence=confidence)

        except Exception as exc:
            # Log + re-raise: the chain marks this attempt failed and escalates; the PHOTO
            # fallback for a fully-exhausted chain is applied by FigureEnricher, not here.
            self.logger.warning(f"VitOnnxClassifier inference failed: {exc}")
            raise

    def _build_session(self) -> Any:
        """
        Build the ONNX Runtime session (the ModelCache loader — invoked once per process).

        Returns:
            Any: A new ``onnxruntime.InferenceSession`` bound to the configured providers.

        Raises:
            Exception: Propagates any onnxruntime import / session-load failure (not cached).
        """
        import onnxruntime as ort  # type: ignore

        providers = (
            ["CUDAExecutionProvider", "CPUExecutionProvider"]
            if self._use_gpu
            else ["CPUExecutionProvider"]
        )
        session = ort.InferenceSession(self._model_path, providers=providers)
        self.logger.info(
            f"VitOnnxClassifier: model loaded from {self._model_path!r} (gpu={self._use_gpu})"
        )
        return session

