# ====== Code Summary ======
# Behaviour of NvidiaDriverDetector against a fake /proc and /dev tree built in a temp directory.

# ====== Standard Library Imports ======
import pathlib

# ====== Internal Project Imports ======
from model_server_core import NvidiaDriverDetector


def _detector(tmp_path: pathlib.Path) -> NvidiaDriverDetector:
    return NvidiaDriverDetector(
        proc_version_path=tmp_path / "proc" / "version", dev_dir=tmp_path / "dev"
    )


def test_proc_version_file_is_a_positive_signal(tmp_path: pathlib.Path) -> None:
    (tmp_path / "proc").mkdir()
    (tmp_path / "proc" / "version").write_text("NVRM version")

    assert _detector(tmp_path).is_cuda_available() is True


def test_device_node_is_a_positive_signal(tmp_path: pathlib.Path) -> None:
    (tmp_path / "dev").mkdir()
    (tmp_path / "dev" / "nvidia0").touch()

    assert _detector(tmp_path).is_cuda_available() is True


def test_unrelated_device_nodes_are_not_a_signal(tmp_path: pathlib.Path) -> None:
    (tmp_path / "dev").mkdir()
    (tmp_path / "dev" / "null").touch()

    assert _detector(tmp_path).is_cuda_available() is False


def test_missing_directories_mean_no_gpu(tmp_path: pathlib.Path) -> None:
    assert _detector(tmp_path).is_cuda_available() is False
