"""App boot + discovery + import hygiene lock (ported from scratchpad test_app_boot.py)."""

import pathlib
import subprocess
import sys


def test_discovery_lists_ingest_pipeline(client) -> None:
    """GET /api/v1/pipelines is the UI's single bootstrap call."""
    response = client.get("/api/v1/pipelines")
    assert response.status_code == 200, response.text
    index = response.json()["pipelines"]
    assert index[0]["key"] == "ingest"
    assert index[0]["design_url"] == "/api/v1/pipelines/ingest"


def test_import_hygiene_backend_stays_light() -> None:
    """Serving the whole design surface must not pull the worker-only heavy model runtimes.

    Run in a subprocess (see _hygiene_probe.py): other unit tests in this session deliberately
    import docling/rapidocr for real, which would make an in-process sys.modules check
    order-dependent and meaningless.
    """
    probe = pathlib.Path(__file__).resolve().parent / "_hygiene_probe.py"
    result = subprocess.run(
        [sys.executable, str(probe)], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr
    sentinel = next(
        (line for line in result.stdout.splitlines() if line.startswith("HYGIENE_RESULT:")), None
    )
    assert sentinel is not None, f"probe produced no result line; stdout={result.stdout!r}"
    loaded = [lib for lib in sentinel.removeprefix("HYGIENE_RESULT:").split(",") if lib]
    assert not loaded, f"backend pulled heavy worker libs: {loaded}"
