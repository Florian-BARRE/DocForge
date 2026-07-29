# ====== Code Summary ======
# Unit tests for ModelRevisionResolver. huggingface_hub.snapshot_download is fully mocked — no
# network calls, no real HF cache access.

# ====== Standard Library Imports ======
from unittest.mock import patch

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from libs.bge_models.revision import ModelRevisionResolver


def test_resolve_bypassed_when_revision_none() -> None:
    """When revision is None, the bare model id is returned and snapshot_download is never called."""
    with patch("libs.bge_models.revision.snapshot_download") as mock_download:
        result = ModelRevisionResolver.resolve("BAAI/bge-m3", None)

    assert result == "BAAI/bge-m3"
    mock_download.assert_not_called()


def test_resolve_bypassed_when_revision_empty_string() -> None:
    """An empty-string revision (env var cleared to opt back into floating) is also a no-op."""
    with patch("libs.bge_models.revision.snapshot_download") as mock_download:
        result = ModelRevisionResolver.resolve("BAAI/bge-reranker-v2-m3", "")

    assert result == "BAAI/bge-reranker-v2-m3"
    mock_download.assert_not_called()


def test_resolve_returns_local_snapshot_path_when_revision_set() -> None:
    """When a revision is set, snapshot_download is called with it and its return path is used."""
    fake_path = "/models/hub/models--BAAI--bge-m3/snapshots/deadbeef"
    with patch("libs.bge_models.revision.snapshot_download", return_value=fake_path) as mock_download:
        result = ModelRevisionResolver.resolve("BAAI/bge-m3", "deadbeef")

    mock_download.assert_called_once_with(repo_id="BAAI/bge-m3", revision="deadbeef")
    assert result == fake_path


def test_resolve_propagates_snapshot_download_failure() -> None:
    """A snapshot_download failure (e.g. network error) is NOT swallowed — fail-fast on a pinned
    deploy that cannot fetch its pinned weights, no silent fallback to floating."""
    with patch(
        "libs.bge_models.revision.snapshot_download", side_effect=OSError("network unreachable")
    ):
        with pytest.raises(OSError, match="network unreachable"):
            ModelRevisionResolver.resolve("BAAI/bge-m3", "deadbeef")


def test_instantiation_is_blocked() -> None:
    """ModelRevisionResolver is a static-only class and must reject direct instantiation."""
    with pytest.raises(TypeError):
        ModelRevisionResolver()
