# ====== Code Summary ======
# Golden-file helper of the SDK characterization suite. A golden is a committed JSON document that
# records TODAY's behaviour of the published SDK; a test compares a freshly computed snapshot with it.
# A diff is a public-contract decision to review, never a test to "fix": regenerate deliberately with
# DOCFORGE_SDK_REGEN_GOLDENS=1 (writes the files, then the test fails once so a regeneration is never
# silently green) and review the diff.

# ====== Standard Library Imports ======
import json
import os
from pathlib import Path
from typing import Any

# ====== Third-Party Library Imports ======
import pytest

_GOLDENS = Path(__file__).resolve().parents[1] / "goldens"
_REGEN_ENV = "DOCFORGE_SDK_REGEN_GOLDENS"

# True when the run is a deliberate regeneration of the goldens (see the module summary).
REGEN = os.environ.get(_REGEN_ENV) == "1"


def load_golden(name: str) -> Any:
    """
    Load a committed golden document.

    Args:
        name (str): The file name inside ``goldens/`` (e.g. ``"public_exports.json"``).

    Returns:
        Any: The decoded JSON document.
    """
    return json.loads((_GOLDENS / name).read_text(encoding="utf-8"))


def assert_matches_golden(name: str, actual: Any) -> None:
    """
    Compare a snapshot with its golden, byte-for-byte after JSON normalisation.

    Args:
        name (str): The golden file name inside ``goldens/``.
        actual (Any): The freshly computed, JSON-serialisable snapshot.
    """
    # 1. Normalise through JSON so tuples/ints/strs compare the way the file stores them.
    normalised = json.loads(json.dumps(actual))
    path = _GOLDENS / name

    # 2. Regeneration is explicit and never green: the run that writes the golden fails once.
    if REGEN:
        path.write_text(
            json.dumps(normalised, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        pytest.fail(f"{name} regenerated: review the diff, then run again without {_REGEN_ENV}")

    # 3. Otherwise the golden is the contract.
    assert path.exists(), f"missing golden {name}: run once with {_REGEN_ENV}=1"
    expected = json.loads(path.read_text(encoding="utf-8"))

    # 4. Name the drifted entries first: a golden is big, the failing keys are what a reviewer reads.
    if isinstance(expected, dict) and isinstance(normalised, dict):
        drifted = sorted(
            key
            for key in expected.keys() | normalised.keys()
            if expected.get(key) != normalised.get(key)
        )
        assert not drifted, f"{name} drifted at: {drifted}"
    assert normalised == expected
