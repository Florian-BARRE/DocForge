# ====== Code Summary ======
# Unit tests for CpuBudgetResolver — pure filesystem-driven cgroup v2 quota parsing.
# No torch/FlagEmbedding involved. Each cgroup case writes a real cpu.max file under tmp_path
# and passes it in via the cgroup_cpu_max_path override, rather than mocking pathlib.

# ====== Standard Library Imports ======
import pathlib

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from libs.bge_models.cpu_budget import CpuBudgetResolver


def _write_cpu_max(tmp_path: pathlib.Path, content: str) -> pathlib.Path:
    """
    Write a fake cgroup v2 cpu.max file and return its path.

    Args:
        tmp_path (pathlib.Path): pytest tmp_path fixture directory.
        content (str): Raw file content, e.g. "400000 100000".

    Returns:
        pathlib.Path: Path to the written file.
    """
    path = tmp_path / "cpu.max"
    path.write_text(content)
    return path


def test_quota_400000_period_100000_resolves_to_4(tmp_path: pathlib.Path) -> None:
    """A 4-CPU quota (400000/100000) resolves to an effective budget of 4, source=cgroup."""
    path = _write_cpu_max(tmp_path, "400000 100000")
    result = CpuBudgetResolver.resolve(cgroup_cpu_max_path=path)
    assert result.cpu_budget == 4
    assert result.source == "cgroup"


def test_quota_200000_period_100000_resolves_to_2(tmp_path: pathlib.Path) -> None:
    """A 2-CPU quota (200000/100000) resolves to an effective budget of 2, source=cgroup."""
    path = _write_cpu_max(tmp_path, "200000 100000")
    result = CpuBudgetResolver.resolve(cgroup_cpu_max_path=path)
    assert result.cpu_budget == 2
    assert result.source == "cgroup"


def test_quota_max_falls_back_to_affinity(tmp_path: pathlib.Path) -> None:
    """quota="max" means unlimited — falls back to the affinity/cpu_count source."""
    path = _write_cpu_max(tmp_path, "max 100000")
    result = CpuBudgetResolver.resolve(cgroup_cpu_max_path=path)
    assert result.source == "affinity"
    assert result.cpu_budget >= 1


def test_missing_file_falls_back_to_affinity(tmp_path: pathlib.Path) -> None:
    """A nonexistent cpu.max path degrades to the affinity/cpu_count fallback, never raises."""
    path = tmp_path / "does_not_exist"
    result = CpuBudgetResolver.resolve(cgroup_cpu_max_path=path)
    assert result.source == "affinity"
    assert result.cpu_budget >= 1


def test_unparseable_content_falls_back_to_affinity(tmp_path: pathlib.Path) -> None:
    """Garbled cpu.max content degrades to the affinity/cpu_count fallback, never raises."""
    path = _write_cpu_max(tmp_path, "not a valid cgroup file")
    result = CpuBudgetResolver.resolve(cgroup_cpu_max_path=path)
    assert result.source == "affinity"
    assert result.cpu_budget >= 1


def test_zero_period_falls_back_to_affinity(tmp_path: pathlib.Path) -> None:
    """A zero period (division-by-zero guard) degrades to the affinity/cpu_count fallback."""
    path = _write_cpu_max(tmp_path, "400000 0")
    result = CpuBudgetResolver.resolve(cgroup_cpu_max_path=path)
    assert result.source == "affinity"
    assert result.cpu_budget >= 1


def test_fractional_quota_floors(tmp_path: pathlib.Path) -> None:
    """A quota that doesn't divide evenly floors to the nearest whole CPU, minimum 1."""
    path = _write_cpu_max(tmp_path, "150000 100000")
    result = CpuBudgetResolver.resolve(cgroup_cpu_max_path=path)
    assert result.cpu_budget == 1
    assert result.source == "cgroup"


def test_instantiation_is_blocked() -> None:
    """CpuBudgetResolver is a static-only class and must reject direct instantiation."""
    with pytest.raises(TypeError):
        CpuBudgetResolver()
