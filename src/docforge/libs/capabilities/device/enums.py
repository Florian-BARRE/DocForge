# ====== Code Summary ======
# Defines the Device and DeviceCapability StrEnums used throughout the capabilities layer.
# These enums declare the available compute devices and the ML capability categories
# that drive fallback chain resolution in DeviceManager.

# ====== Standard Library Imports ======
from __future__ import annotations

from enum import StrEnum


class Device(StrEnum):
    """Available compute devices for ML workloads."""

    GPU = "gpu"
    CPU = "cpu"
    REMOTE = "remote"  # API-backed provider (no local inference)


class DeviceCapability(StrEnum):
    """ML capability categories used to select the right device fallback chain."""

    PARSE = "parse"      # Layout / structure parsing (Docling, MinerU…)
    OCR = "ocr"          # Optical character recognition
    VLM = "vlm"          # Vision-language model
    EMBED = "embed"      # Text embedding
    RERANK = "rerank"    # Cross-encoder reranking
    CLASSIFY = "classify"  # Figure classifier (small ViT)
