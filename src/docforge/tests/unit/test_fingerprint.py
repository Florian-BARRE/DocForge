# ====== Code Summary ======
# Unit tests for libs/pipeline/fingerprint.py — deterministic Merkle-DAG fingerprinting.

import pytest

from pipeline.fingerprint import compute_call_fingerprint, compute_fingerprint


class TestComputeFingerprint:
    """Tests for the pipeline node fingerprint function."""

    def test_returns_64_char_hex(self) -> None:
        """Output is a 64-character hex string (blake3 digest)."""
        fp = compute_fingerprint("s0", "1.0", {}, [])
        assert isinstance(fp, str)
        assert len(fp) == 64
        assert all(c in "0123456789abcdef" for c in fp)

    def test_deterministic(self) -> None:
        """Same inputs always produce the same fingerprint."""
        fp1 = compute_fingerprint("s1", "1.0", {"backend": "docling"}, ["upstream_fp"])
        fp2 = compute_fingerprint("s1", "1.0", {"backend": "docling"}, ["upstream_fp"])
        assert fp1 == fp2

    def test_different_node_type_changes_fingerprint(self) -> None:
        """Changing node_type invalidates the fingerprint."""
        fp_a = compute_fingerprint("s0", "1.0", {}, [])
        fp_b = compute_fingerprint("s1", "1.0", {}, [])
        assert fp_a != fp_b

    def test_different_code_version_changes_fingerprint(self) -> None:
        """Bumping code_version invalidates the fingerprint (cache miss)."""
        fp_old = compute_fingerprint("s0", "1.0", {}, [])
        fp_new = compute_fingerprint("s0", "2.0", {}, [])
        assert fp_old != fp_new

    def test_different_params_changes_fingerprint(self) -> None:
        """Any param change invalidates the fingerprint."""
        fp_a = compute_fingerprint("s4", "1.0", {"max_tokens": 512}, [])
        fp_b = compute_fingerprint("s4", "1.0", {"max_tokens": 256}, [])
        assert fp_a != fp_b

    def test_param_key_order_is_stable(self) -> None:
        """Dict key insertion order must not affect the fingerprint (sort_keys=True)."""
        fp_a = compute_fingerprint("s0", "1.0", {"z": 1, "a": 2}, [])
        fp_b = compute_fingerprint("s0", "1.0", {"a": 2, "z": 1}, [])
        assert fp_a == fp_b

    def test_input_fingerprint_order_matters(self) -> None:
        """Input fingerprints are ordered (DAG edge direction is preserved)."""
        fp_ab = compute_fingerprint("s2", "1.0", {}, ["fp_a", "fp_b"])
        fp_ba = compute_fingerprint("s2", "1.0", {}, ["fp_b", "fp_a"])
        assert fp_ab != fp_ba

    def test_empty_inputs_produces_valid_fingerprint(self) -> None:
        """No upstream nodes is a valid state (root node)."""
        fp = compute_fingerprint("s0", "1.0", {}, [])
        assert len(fp) == 64

    def test_adding_upstream_changes_fingerprint(self) -> None:
        """Adding an upstream dependency changes the fingerprint (cache miss)."""
        fp_alone = compute_fingerprint("s1", "1.0", {}, [])
        fp_chained = compute_fingerprint("s1", "1.0", {}, ["abc123"])
        assert fp_alone != fp_chained

    def test_nested_param_dict_stability(self) -> None:
        """Nested param dicts are serialised canonically."""
        fp_a = compute_fingerprint("s2", "1.0", {"nested": {"b": 2, "a": 1}}, [])
        fp_b = compute_fingerprint("s2", "1.0", {"nested": {"a": 1, "b": 2}}, [])
        assert fp_a == fp_b


class TestComputeCallFingerprint:
    """Tests for the provider-call cache key function."""

    def test_returns_64_char_hex(self) -> None:
        """Output is a 64-character hex blake3 digest."""
        fp = compute_call_fingerprint("ocr", "paddle", "1.0", {}, "sha256abc")
        assert len(fp) == 64

    def test_deterministic(self) -> None:
        """Same inputs always produce the same key."""
        fp1 = compute_call_fingerprint("ocr", "mistral", "2024-12", {"lang": "fr"}, "aabb")
        fp2 = compute_call_fingerprint("ocr", "mistral", "2024-12", {"lang": "fr"}, "aabb")
        assert fp1 == fp2

    def test_different_capability_changes_key(self) -> None:
        """OCR and embed calls on the same content must have different keys."""
        fp_ocr = compute_call_fingerprint("ocr", "paddle", "1.0", {}, "aabb")
        fp_embed = compute_call_fingerprint("embed", "paddle", "1.0", {}, "aabb")
        assert fp_ocr != fp_embed

    def test_different_content_hash_changes_key(self) -> None:
        """Different documents produce different cache keys."""
        fp_a = compute_call_fingerprint("ocr", "paddle", "1.0", {}, "hash_a")
        fp_b = compute_call_fingerprint("ocr", "paddle", "1.0", {}, "hash_b")
        assert fp_a != fp_b

    def test_param_order_stable(self) -> None:
        """Dict insertion order must not affect the cache key."""
        fp_a = compute_call_fingerprint("vlm", "qwen", "1.0", {"z": 1, "a": 2}, "h")
        fp_b = compute_call_fingerprint("vlm", "qwen", "1.0", {"a": 2, "z": 1}, "h")
        assert fp_a == fp_b

    def test_different_provider_version_changes_key(self) -> None:
        """Upgrading the provider model must invalidate cached results."""
        fp_old = compute_call_fingerprint("ocr", "mistral", "2024-01", {}, "aabb")
        fp_new = compute_call_fingerprint("ocr", "mistral", "2024-12", {}, "aabb")
        assert fp_old != fp_new
