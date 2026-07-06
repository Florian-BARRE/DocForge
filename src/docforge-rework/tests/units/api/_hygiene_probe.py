# ====== Code Summary ======
# Standalone probe run in an ISOLATED subprocess by test_app_boot.py's import-hygiene test.
# It boots the app exactly like uvicorn would and reports which heavy worker-only libraries got
# pulled into sys.modules. Must run out-of-process: within the main test session, other unit
# tests deliberately import docling/rapidocr for real (see tests/units/nodes/), which would
# permanently pollute sys.modules and make an in-process check meaningless after the first run.

# ====== Standard Library Imports ======
import pathlib
import sys
import types

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _register_shared_libs_alias() -> None:
    module = types.ModuleType("shared_libs")
    module.__path__ = [str(REPO_ROOT / "shared" / "libs")]
    sys.modules["shared_libs"] = module


def main() -> None:
    _register_shared_libs_alias()
    sys.path.insert(0, str(REPO_ROOT / "app"))
    from entrypoint import app  # noqa: PLC0415
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.get("/api/v1/pipelines/ingest?full=true")
    assert response.status_code == 200, response.text

    heavy = ("docling", "rapidocr_onnxruntime", "pypdfium2", "onnxruntime")
    loaded = [lib for lib in heavy if lib in sys.modules]
    # A sentinel-prefixed line: loggerplusplus also writes to stdout, so the raw output is not
    # safe to parse directly — the caller greps for this exact prefix.
    print(f"HYGIENE_RESULT:{','.join(loaded)}")


if __name__ == "__main__":
    main()
