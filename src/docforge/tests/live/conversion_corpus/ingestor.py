# ====== Code Summary ======
# Drives the real API for the conversion corpus: creates one throwaway collection, uploads every
# corpus document, polls each ingestion job to a terminal state and fetches the artefacts a
# fingerprint is made of (document facts, chunks, canonical IR, markdown, job status). The
# collection is always deleted on exit.

# ====== Standard Library Imports ======
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

# ====== Third-Party Library Imports ======
import httpx

# ====== Local Project Imports ======
from .corpus import CorpusDocument

JOB_POLL_INTERVAL_SECONDS = 2.0
JOB_TIMEOUT_SECONDS = 600.0
TERMINAL_JOB_STATES = {"done", "failed", "cancelled"}


class IngestionFailedError(RuntimeError):
    """A corpus document's ingestion job did not finish ``done``."""


@dataclass
class IngestedDocument:
    """Everything the API returned for one ingested corpus document (raw, un-normalised)."""

    key: str
    document_id: str
    job: dict[str, Any]
    document: dict[str, Any]
    chunks: list[dict[str, Any]]
    ir: dict[str, Any]
    markdown: str
    trace: dict[str, Any]
    extras: dict[str, Any] = field(default_factory=dict)


class CorpusIngestor:
    """Ingests the corpus into a temporary collection of the running stack."""

    def __init__(self, client: httpx.Client, formats: list[str], with_embed: bool = False) -> None:
        self._client = client
        self._formats = formats
        self._with_embed = with_embed
        self._collection_id: str | None = None

    def __enter__(self) -> "CorpusIngestor":
        response = self._client.post(
            "/api/v1/collections",
            json={
                "name": f"conversion-corpus-{uuid.uuid4().hex[:8]}",
                "supported_formats": self._formats,
                "max_file_size_bytes": 10_000_000,
            },
        )
        response.raise_for_status()
        created = response.json()
        self._collection_id = created["id"]
        if not self._with_embed:
            self._disable_embed_stage(created["pipeline"])
        return self

    def _disable_embed_stage(self, stock_blob: dict[str, Any]) -> None:
        """Drops the embed stage: conversion (parse + chunk) is what the corpus fingerprints, and
        embedding needs the BGE model host, which a smoke run need not carry."""
        applied = self._client.post(
            "/api/v1/pipelines/ingest/stages/apply",
            json={"blob": stock_blob, "action": {"action": "disable_stage", "stage": "embed"}},
        )
        applied.raise_for_status()
        patched = self._client.patch(
            f"/api/v1/collections/{self._collection_id}", json={"pipeline": applied.json()["blob"]}
        )
        patched.raise_for_status()

    def __exit__(self, *_exc: object) -> None:
        if self._collection_id:
            self._client.delete(f"/api/v1/collections/{self._collection_id}")

    def ingest(self, document: CorpusDocument) -> IngestedDocument:
        """Uploads one document, waits for its job and fetches the artefacts."""
        response = self._client.post(
            "/api/v1/documents",
            files={"file": (document.path.name, document.read_bytes(), document.mime_type)},
            data={"collection_id": self._collection_id, "metadata": "{}"},
        )
        response.raise_for_status()
        accepted = response.json()
        job = self._wait_for_job(accepted["job_id"], document.key)
        document_id = accepted["document_id"]
        return IngestedDocument(
            key=document.key,
            document_id=document_id,
            job=job,
            document=self._get_json(f"/api/v1/documents/{document_id}"),
            chunks=self._get_json(f"/api/v1/documents/{document_id}/chunks"),
            ir=self._get_json(f"/api/v1/documents/{document_id}/ir"),
            markdown=self._client.get(f"/api/v1/documents/{document_id}/markdown").text,
            trace=self._get_json(f"/api/v1/jobs/{accepted['job_id']}/events"),
        )

    def _get_json(self, url: str) -> Any:
        response = self._client.get(url)
        response.raise_for_status()
        return response.json()

    def _wait_for_job(self, job_id: str, key: str) -> dict[str, Any]:
        deadline = time.monotonic() + JOB_TIMEOUT_SECONDS
        while True:
            job = self._get_json(f"/api/v1/jobs/{job_id}")
            if job["status"] in TERMINAL_JOB_STATES:
                if job["status"] != "done":
                    raise IngestionFailedError(
                        f"{key}: job {job_id} ended {job['status']}: "
                        f"{json.dumps({k: job.get(k) for k in ('error', 'error_type', 'failed_node_id', 'failed_node_kind')})}"
                    )
                return job
            if time.monotonic() > deadline:
                raise IngestionFailedError(
                    f"{key}: job {job_id} still {job['status']} after {JOB_TIMEOUT_SECONDS}s"
                )
            time.sleep(JOB_POLL_INTERVAL_SECONDS)
