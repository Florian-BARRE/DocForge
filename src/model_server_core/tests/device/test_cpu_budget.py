# ====== Code Summary ======
# Behaviour of CpuBudget against fake cgroup v2 cpu.max files: the quota wins, anything unusable falls
# back to the scheduler-affinity count, and the resolver never raises.

# ====== Standard Library Imports ======
import os
import pathlib

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from model_server_core import CpuBudget


def _cpu_max(tmp_path: pathlib.Path, content: str) -> pathlib.Path:
    path = tmp_path / "cpu.max"
    path.write_text(content)
    return path


def _affinity() -> int:
    return len(os.sched_getaffinity(0))


@pytest.mark.parametrize(
    ("content", "expected"),
    [("400000 100000\n", 4), ("150000 100000", 1), ("50000 100000", 1), ("1000000 100000", 10)],
)
def test_the_cgroup_quota_is_floor_quota_over_period_at_least_one(
    tmp_path: pathlib.Path, content: str, expected: int
) -> None:
    resolved = CpuBudget(_cpu_max(tmp_path, content)).resolve()

    assert (resolved.cpu_budget, resolved.source) == (expected, "cgroup")


@pytest.mark.parametrize("content", ["max 100000", "garbage", "", "1 2 3", "10 0", "x y"])
def test_unusable_quota_falls_back_to_affinity(tmp_path: pathlib.Path, content: str) -> None:
    resolved = CpuBudget(_cpu_max(tmp_path, content)).resolve()

    assert (resolved.cpu_budget, resolved.source) == (_affinity(), "affinity")


def test_missing_file_falls_back_to_affinity(tmp_path: pathlib.Path) -> None:
    resolved = CpuBudget(tmp_path / "absent").resolve()

    assert (resolved.cpu_budget, resolved.source) == (_affinity(), "affinity")


def test_without_sched_getaffinity_the_cpu_count_is_used(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delattr(os, "sched_getaffinity")
    monkeypatch.setattr(os, "cpu_count", lambda: 6)

    assert CpuBudget(tmp_path / "absent").resolve().cpu_budget == 6


def test_unknown_cpu_count_still_yields_one(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delattr(os, "sched_getaffinity")
    monkeypatch.setattr(os, "cpu_count", lambda: None)

    assert CpuBudget(tmp_path / "absent").resolve().cpu_budget == 1
