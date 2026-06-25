# ====== Code Summary ======
# Unit tests for VitOnnxConfig availability/selectability honesty.  build() raises when no
# usable model_path exists, so the discovery surface must report vit_onnx as NOT available and
# NOT selectable (with a "requires model_path" note) when no model is configured, and as
# available/selectable when a real .onnx path is supplied.

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from common_libs.providers.classifier.vit_onnx.config import VitOnnxConfig


class TestVitOnnxAvailability:
    """vit_onnx must not advertise itself as usable when no model_path is configured."""

    def test_not_available_without_model_path(self) -> None:
        """The discovery default (no model_path) reports not available + a config note."""
        available, note = VitOnnxConfig.availability(None)
        assert available is False
        assert "model_path" in note
        assert ".onnx" in note

    def test_not_selectable_without_model_path(self) -> None:
        """The discovery default (no model_path) reports not selectable."""
        assert VitOnnxConfig.selectable(None) is False

    def test_not_available_with_missing_file(self) -> None:
        """A non-existent path is still not available — build() would raise on it."""
        available, _note = VitOnnxConfig.availability(None, model_path="/does/not/exist.onnx")
        assert available is False

    def test_available_with_valid_model_path(self, tmp_path) -> None:
        """A real, existing .onnx file makes vit_onnx available and selectable."""
        # 1. Create an on-disk model file the availability probe can stat.
        model_file = tmp_path / "classifier.onnx"
        model_file.write_bytes(b"\x00onnx")

        # 2. Both availability and selectable must report usable.
        available, note = VitOnnxConfig.availability(None, model_path=str(model_file))
        assert available is True
        assert "configured" in note
        assert VitOnnxConfig.selectable(None, model_path=str(model_file)) is True
