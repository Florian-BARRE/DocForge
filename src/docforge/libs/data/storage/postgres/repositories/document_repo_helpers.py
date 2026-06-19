# ====== Code Summary ======
# Static helpers for DocumentRepository: pure, stateless utilities for query-building
# and result post-processing that do not require a session or instance state.

# ====== Standard Library Imports ======
from typing import Any

# ====== Third-Party Library Imports ======
from loggerplusplus import loggerplusplus

# ====== Local Project Imports ======
from ..models import DocumentModel

# Status rank used to select the best observed status when a node has been retried.
# Higher rank wins: done > running > pending > failed.
_STAGE_STATUS_RANK: dict[str, int] = {
    "done": 4,
    "running": 3,
    "pending": 2,
    "failed": 1,
}

# Allowed sort columns for list_by_collection — maps client-facing sort_by keys
# to the corresponding SQLAlchemy column expressions.
_SORT_COLUMNS: dict[str, Any] = {
    "created_at": DocumentModel.created_at,
    "filename": DocumentModel.filename,
    "status": DocumentModel.status,
    "file_size": DocumentModel.file_size,
}


class DocumentRepoHelpers:
    """
    Pure, stateless helpers for DocumentRepository.

    Extracts query-building and result post-processing utilities that do not
    depend on a database session or instance state, keeping DocumentRepository
    focused on async data-access operations.
    """

    logger = loggerplusplus.bind(identifier="DocumentRepoHelpers")

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only helper class."""
        raise TypeError("DocumentRepoHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def resolve_sort_column(sort_by: str) -> Any:
        """
        Resolve a sort_by key to the corresponding SQLAlchemy column expression.

        Defaults to ``DocumentModel.created_at`` for unknown keys, ensuring the
        query always has a stable sort even with invalid client input.

        Args:
            sort_by (str): Sort key — one of ``created_at``, ``filename``,
                ``status``, ``file_size``.

        Returns:
            Any: SQLAlchemy column expression for the requested sort column.
        """
        return _SORT_COLUMNS.get(sort_by, DocumentModel.created_at)

    @staticmethod
    def rank_stage_statuses(rows: list[tuple[str, str]]) -> dict[str, str]:
        """
        Collapse multiple stage-run rows to a single best-status per node.

        When a pipeline node has been retried, the ranking
        ``done > running > pending > failed`` is applied so a later successful
        run supersedes an older failure.

        Args:
            rows (list[tuple[str, str]]): Raw ``(node_id, status)`` pairs from
                the database (may contain duplicate node_ids across retries).

        Returns:
            dict[str, str]: ``{node_id: best_status}`` — one entry per node.
        """
        # 1. Fold rows: keep the highest-ranked status seen per node_id
        summary: dict[str, str] = {}
        for node_id, status in rows:
            current_rank = _STAGE_STATUS_RANK.get(summary.get(node_id, ""), 0)
            incoming_rank = _STAGE_STATUS_RANK.get(status, 0)
            if incoming_rank > current_rank:
                summary[node_id] = status
        return summary
