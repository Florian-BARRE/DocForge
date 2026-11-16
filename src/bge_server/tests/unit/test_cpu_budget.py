# ====== Code Summary ======
# Unit tests for the core CpuBudget as the BGE loader uses it — pure filesystem-driven cgroup v2 quota
# parsing (the resolver moved to model_server_core in R-27 step 2; these cases stay as bge's net).
# No torch/FlagEmbedding involved. Each cgroup case writes a real cpu.max file under tmp_path
# and passes it in via the cgroup_cpu_max_path override, rather than mocking pathlib.

# ====== Standard Library Imports ======
import pathlib

# ====== Third-Party Library Imports ======
# ====== Internal Project Imports ======
from model_server_core import CpuBudget

from libs.bge_models import model_loader


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
    result = CpuBudget(path).resolve()
    assert result.cpu_budget == 4
    assert result.source == "cgroup"


def test_quota_200000_period_100000_resolves_to_2(tmp_path: pathlib.Path) -> None:
    """A 2-CPU quota (200000/100000) resolves to an effective budget of 2, source=cgroup."""
    path = _write_cpu_max(tmp_path, "200000 100000")
    result = CpuBudget(path).resolve()
    assert result.cpu_budget == 2
    assert result.source == "cgroup"


def test_quota_max_falls_back_to_affinity(tmp_path: pathlib.Path) -> None:
    """quota="max" means unlimited — falls back to the affinity/cpu_count source."""
    path = _write_cpu_max(tmp_path, "max 100000")
    result = CpuBudget(path).resolve()
    assert result.source == "affinity"
    assert result.cpu_budget >= 1


def test_missing_file_falls_back_to_affinity(tmp_path: pathlib.Path) -> None:
    """A nonexistent cpu.max path degrades to the affinity/cpu_count fallback, never raises."""
    path = tmp_path / "does_not_exist"
    result = CpuBudget(path).resolve()
    assert result.source == "affinity"
    assert result.cpu_budget >= 1


def test_unparseable_content_falls_back_to_affinity(tmp_path: pathlib.Path) -> None:
    """Garbled cpu.max content degrades to the affinity/cpu_count fallback, never raises."""
    path = _write_cpu_max(tmp_path, "not a valid cgroup file")
    result = CpuBudget(path).resolve()
    assert result.source == "affinity"
    assert result.cpu_budget >= 1


def test_zero_period_falls_back_to_affinity(tmp_path: pathlib.Path) -> None:
    """A zero period (division-by-zero guard) degrades to the affinity/cpu_count fallback."""
    path = _write_cpu_max(tmp_path, "400000 0")
    result = CpuBudget(path).resolve()
    assert result.source == "affinity"
    assert result.cpu_budget >= 1


def test_fractional_quota_floors(tmp_path: pathlib.Path) -> None:
    """A quota that doesn't divide evenly floors to the nearest whole CPU, minimum 1."""
    path = _write_cpu_max(tmp_path, "150000 100000")
    result = CpuBudget(path).resolve()
    assert result.cpu_budget == 1
    assert result.source == "cgroup"


def test_the_model_loader_budgets_threads_with_the_core_cpu_budget() -> None:
    """The torch thread cap is derived from the shared core CpuBudget, not a bge copy."""
    assert model_loader.CpuBudget is CpuBudget
