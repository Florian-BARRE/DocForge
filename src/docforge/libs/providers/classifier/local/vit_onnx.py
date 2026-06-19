# ====== Code Summary ======
# ViT ONNX figure classifier — loads a small Vision Transformer model from an ONNX file.
# Provides higher accuracy than LayoutLabelsClassifier when a trained model is available.
# Falls back to PHOTO (confidence 0.5) gracefully if the model file is absent.

from __future__ import annotations

import io

from loggerplusplus import LoggerClass

from libs.capabilities.classifier.base import ClassificationResult, FigureClassifier
from libs.core.ir.models import FigureKind

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
        self._session = None   # Lazy-loaded on first classify() call

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

        Returns PHOTO at confidence 0.5 if the model is unavailable or inference fails.
        """
        try:
            import numpy as np  # type: ignore
            import onnxruntime as ort  # type: ignore
            from PIL import Image  # type: ignore

            # 1. Lazy-load the ONNX Runtime session
            if self._session is None:
                providers = (
                    ["CUDAExecutionProvider", "CPUExecutionProvider"]
                    if self._use_gpu
                    else ["CPUExecutionProvider"]
                )
                self._session = ort.InferenceSession(self._model_path, providers=providers)
                self.logger.info(
                    f"VitOnnxClassifier: model loaded from {self._model_path!r} "
                    f"(gpu={self._use_gpu})"
                )

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
            input_name = self._session.get_inputs()[0].name
            logits = self._session.run(None, {input_name: arr})[0][0]

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
            self.logger.warning(
                f"VitOnnxClassifier inference failed: {exc} — falling back to PHOTO"
            )
            return ClassificationResult(kind=FigureKind.PHOTO, confidence=0.5)

