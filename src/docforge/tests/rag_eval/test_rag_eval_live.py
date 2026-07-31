"""Live RAG-benchmark smoke test — a tiny end-to-end run against the RUNNING stack.

Skips unless DOCFORGE_TOKEN is exported and the API answers. Ingests a few QASPER papers on the
default pipeline (no LLM/VLM — zero API cost) and asserts the benchmark loop actually retrieves the
gold evidence for at least some questions. It does NOT assert a precise score (that is the runner's
job); it guards that the harness end-to-end works. Run with:

    DOCFORGE_TOKEN=$(docker compose ... exec -T docforge_app printenv AUTH_ROOT_TOKEN | tr -d '\\r') \\
      uv run pytest tests/rag_eval/test_rag_eval_live.py -m live -s
"""

import pytest

from tests.rag_eval.harness import client_from_env, run_eval
from tests.rag_eval.qasper import load_papers


@pytest.mark.live
def test_qasper_slice_ingests_and_retrieves_evidence() -> None:
    client = client_from_env()
    if client is None:
        pytest.skip("set DOCFORGE_TOKEN (and DOCFORGE_API_BASE) + run the stack to exercise this")

    papers = load_papers(3)
    assert papers, "QASPER slice failed to load (network?)"

    report = run_eval(client, papers, label="live-smoke", ks=(1, 5, 10), keep_collection=False)
    client.close()

    # 1. The pipeline actually ingested the papers end to end.
    assert report.ingested == report.papers, (
        f"only {report.ingested}/{report.papers} papers ingested"
    )
    assert report.questions > 0, "no answerable questions in the slice"
    # 2. Retrieval is not dead: at least some questions surface their gold evidence in the top-10.
    assert report.metrics.hit_at[10] > 0.0, "no question retrieved its evidence — retrieval broken"
