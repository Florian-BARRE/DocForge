# ====== Code Summary ======
# Behaviour of CpuFeatureProbe against fake cpuinfo files: exact flag tokens, ARM "Features", caching,
# and the "assume supported" degradation whenever absence cannot be proven.

# ====== Standard Library Imports ======
import pathlib

# ====== Third-Party Library Imports ======
import pytest
from loggerplusplus.testing import capture

# ====== Internal Project Imports ======
from model_server_core import CpuFeatureProbe


def _cpuinfo(tmp_path: pathlib.Path, content: str) -> pathlib.Path:
    path = tmp_path / "cpuinfo"
    path.write_text(content)
    return path


def test_flag_present_in_the_flags_line(tmp_path: pathlib.Path) -> None:
    probe = CpuFeatureProbe(_cpuinfo(tmp_path, "processor : 0\nflags\t\t: fpu sse avx avx2\n"))

    assert probe.supports("avx") is True
    assert probe.supports("avx2") is True


def test_flag_absent_is_a_positive_negative_and_is_logged(tmp_path: pathlib.Path) -> None:
    probe = CpuFeatureProbe(_cpuinfo(tmp_path, "flags : fpu sse sse2\n"))

    with capture(level="ERROR") as logs:
        assert probe.supports("avx") is False

    assert "lacks the 'avx' flag" in logs


def test_flag_match_is_an_exact_token_not_a_substring(tmp_path: pathlib.Path) -> None:
    probe = CpuFeatureProbe(_cpuinfo(tmp_path, "flags : fpu avx512f\n"))

    assert probe.supports("avx") is False
    assert probe.supports("avx512f") is True


def test_arm_features_line_is_understood(tmp_path: pathlib.Path) -> None:
    probe = CpuFeatureProbe(_cpuinfo(tmp_path, "Features : fp asimd neon\n"))

    assert probe.supports("neon") is True
    assert probe.supports("avx") is False


@pytest.mark.parametrize("content", ["", "processor : 0\nmodel name : mystery\n"])
def test_no_flags_line_assumes_supported(tmp_path: pathlib.Path, content: str) -> None:
    probe = CpuFeatureProbe(_cpuinfo(tmp_path, content))

    with capture(level="WARNING") as logs:
        assert probe.supports("avx") is True

    assert "assuming supported" in logs


def test_unreadable_file_assumes_supported(tmp_path: pathlib.Path) -> None:
    probe = CpuFeatureProbe(tmp_path / "does-not-exist")

    with capture(level="WARNING") as logs:
        assert probe.supports("avx") is True

    assert "Could not read" in logs


def test_the_file_is_read_once(tmp_path: pathlib.Path) -> None:
    path = _cpuinfo(tmp_path, "flags : avx\n")
    probe = CpuFeatureProbe(path)
    assert probe.supports("avx") is True

    path.write_text("flags : fpu\n")

    assert probe.supports("avx") is True
