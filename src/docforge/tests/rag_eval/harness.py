# ====== Code Summary ======
# The RAG-benchmark harness: a thin DocForge REST client + the eval loop. It ingests a slice of
# QASPER papers into a fresh collection built on a chosen CHUNK config (so min_tokens/target_tokens
# can be swept), then for every question runs the collection's hybrid search and scores whether a
# retrieved chunk COVERS the gold evidence (metrics.py). `compare_configs` runs the same slice under
# two chunk settings so the effect of structure-aware granularity is measured, not guessed. All calls
# go through the public API — no store access — so this exercises exactly what a data scientist gets.

# ====== Standard Library Imports ======
import os
import time
from dataclasses import dataclass

# ====== Third-Party Library Imports ======
import httpx

# ====== Local Project Imports ======
from tests.rag_eval.metrics import Aggregate, aggregate, evaluate_query
from tests.rag_eval.qasper import Paper


class DocForgeClient:
    """Minimal synchronous REST client for the DocForge API used by the benchmark."""

    def __init__(self, base_url: str, token: str, timeout: float = 120.0) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def default_ingest_blob(self) -> dict:
        """The stock ingestion pipeline blob (the product default)."""
        return self._client.get("/pipelines/ingest").raise_for_status().json()["blob"]

    def _apply(self, blob: dict, stage: str, overrides: dict) -> dict:
        """
        Recompile the blob with a stage node's config MERGED with ``overrides`` (not replaced).

        set_config replaces the whole config dict, so we first read the node's current config from the
        blob and merge — otherwise overriding one field (e.g. embed batch_size) would drop the
        provider's required base_url/model and the blob would fail validation at collection creation.
        """
        current = next(
            (node.get("config", {}) for node in blob.get("nodes", []) if node.get("id") == stage),
            {},
        )
        merged = {**current, **overrides}
        response = self._client.post(
            "/pipelines/ingest/stages/apply",
            json={
                "blob": blob,
                "action": {"action": "set_config", "stage": stage, "config": merged},
            },
        )
        return response.raise_for_status().json()["blob"]

    def chunk_blob(self, min_tokens: int | None, target_tokens: int | None) -> dict:
        """
        Build the benchmark pipeline: the chunk config to sweep + a CPU-safe embed config.

        The stock embed batch (32 texts / 60 s) can breach its own timeout on a CPU-hosted BGE-M3
        when a long paper yields many chunks — a deployment reality, not a pipeline bug. The benchmark
        collection therefore embeds in smaller batches with a generous timeout so ingestion is robust
        on this stack; on a GPU host the product defaults are fine.
        """
        blob = self.default_ingest_blob()
        chunk_config: dict = {}
        if min_tokens is not None:
            chunk_config["min_tokens"] = min_tokens
        if target_tokens is not None:
            chunk_config["target_tokens"] = target_tokens
        if chunk_config:
            blob = self._apply(blob, "chunk", chunk_config)
        return self._apply(blob, "embed", {"batch_size": 8, "timeout_seconds": 180.0})

    def create_collection(self, name: str, pipeline: dict) -> str:
        response = self._client.post(
            "/collections",
            json={
                "name": name,
                "supported_formats": ["html"],
                "max_file_size_bytes": 20_000_000,
                "fields": [],
                "pipeline": pipeline,
            },
        )
        return response.raise_for_status().json()["id"]

    def delete_collection(self, collection_id: str) -> None:
        self._client.delete(f"/collections/{collection_id}")

    def upload(self, collection_id: str, filename: str, html: str) -> str:
        response = self._client.post(
            "/documents",
            files={"file": (filename, html.encode("utf-8"), "text/html")},
            data={"collection_id": collection_id},
        )
        return response.raise_for_status().json()["job_id"]

    def wait(self, job_id: str, poll: float = 2.0, deadline: float = 180.0) -> str:
        elapsed = 0.0
        while elapsed < deadline:
            status = self._client.get(f"/jobs/{job_id}").raise_for_status().json()["status"]
            if status in ("done", "failed", "error"):
                return status
            time.sleep(poll)
            elapsed += poll
        return "timeout"

    def search(self, collection_id: str, query: str, limit: int, retries: int = 2) -> list[str]:
        """
        Top-`limit` chunk texts for a query, best-first (the ranked list the metric scores).

        The search pipeline has its own wall-clock cap and, on a CPU-bound / contended embedder, a
        cold query encode can breach it (surfaced as a 422 by the API). That is transient, so retry a
        couple of times; a query that still fails scores as an empty ranking (a miss) rather than
        aborting the whole benchmark.
        """
        for attempt in range(retries + 1):
            response = self._client.post(
                f"/collections/{collection_id}/search", json={"query": query, "limit": limit}
            )
            if response.status_code == 200:
                return [hit.get("text") or "" for hit in response.json().get("hits", [])]
            if response.status_code == 422 and "exceeded" in response.text and attempt < retries:
                continue  # embedder was cold/contended — retry
            break
        return []


_DEFAULT_BASE = "http://localhost:10040/api/v1"


def client_from_env() -> DocForgeClient | None:
    """Build a client from DOCFORGE_API_BASE + DOCFORGE_TOKEN, or None when the token is unset.

    Keeps the harness credential-free: the caller (a live test or an agent runner) exports the token
    it fetched from the stack; nothing here reads a secret off disk or hardcodes one.
    """
    token = os.environ.get("DOCFORGE_TOKEN")
    if not token:
        return None
    base = os.environ.get("DOCFORGE_API_BASE", _DEFAULT_BASE)
    try:
        client = DocForgeClient(base, token)
        client.default_ingest_blob()  # reachability + auth probe
        return client
    except httpx.HTTPError:
        return None


@dataclass(frozen=True)
class EvalReport:
    """The outcome of one benchmark run under one chunk config."""

    label: str
    metrics: Aggregate
    papers: int
    ingested: int
    questions: int
    collection_id: str


def run_eval(
    client: DocForgeClient,
    papers: list[Paper],
    *,
    label: str,
    min_tokens: int | None = None,
    target_tokens: int | None = None,
    ks: tuple[int, ...] = (1, 3, 5, 10),
    search_limit: int = 10,
    keep_collection: bool = True,
) -> EvalReport:
    """
    Ingest the papers under one chunk config and score retrieval over all their questions.

    Args:
        client (DocForgeClient): The API client.
        papers (list[Paper]): The QASPER slice to evaluate.
        label (str): Human label for this run (e.g. "min_tokens=0").
        min_tokens (int | None): Chunk min_tokens override (None = product default).
        target_tokens (int | None): Chunk target_tokens override (None = product default).
        ks (tuple[int, ...]): hit@k cut-offs to report.
        search_limit (int): How many chunks to retrieve per query.
        keep_collection (bool): Leave the collection for inspection (True) or delete it.

    Returns:
        EvalReport: The aggregate metrics + run counts + the collection id.
    """
    pipeline = client.chunk_blob(min_tokens, target_tokens)
    collection_id = client.create_collection(f"ragbench-{label}-{int(time.time())}", pipeline)

    ingested = 0
    for paper in papers:
        job = client.upload(collection_id, f"{paper.paper_id}.html", paper.to_html())
        if client.wait(job) == "done":
            ingested += 1

    results = []
    for paper in papers:
        for question in paper.questions:
            ranked = client.search(collection_id, question.question, search_limit)
            results.append(evaluate_query(ranked, question.evidences))

    if not keep_collection:
        client.delete_collection(collection_id)

    return EvalReport(
        label=label,
        metrics=aggregate(results, ks),
        papers=len(papers),
        ingested=ingested,
        questions=len(results),
        collection_id=collection_id,
    )


def compare_configs(
    client: DocForgeClient,
    papers: list[Paper],
    configs: list[tuple[str, int | None, int | None]],
    **kwargs: object,
) -> list[EvalReport]:
    """Run the same paper slice under several (label, min_tokens, target_tokens) chunk configs."""
    return [
        run_eval(client, papers, label=label, min_tokens=mn, target_tokens=tg, **kwargs)  # type: ignore[arg-type]
        for label, mn, tg in configs
    ]


__all__ = [
    "DocForgeClient",
    "client_from_env",
    "EvalReport",
    "run_eval",
    "compare_configs",
]
