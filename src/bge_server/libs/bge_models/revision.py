# ====== Code Summary ======
# Provides ModelRevisionResolver — a static-only helper that pins a HuggingFace model to an exact
# commit by downloading its snapshot to the local HF cache and returning the LOCAL PATH, which is
# then handed to BGEM3FlagModel / FlagReranker as `model_name_or_path` instead of the bare repo id.
#
# Why a local path instead of `revision=`: BGEM3FlagModel/FlagReranker accept **kwargs but never
# forward them into their internal `AutoTokenizer.from_pretrained` / `AutoModel.from_pretrained`
# calls (verified against the installed FlagEmbedding 1.4.0 — `revision=` is silently swallowed by
# `setattr(self, k, v)` and never reaches the HF download call). Pre-resolving the snapshot with
# `huggingface_hub.snapshot_download(repo_id, revision=...)` and passing that directory instead of
# the repo id sidesteps the dead kwarg entirely: `from_pretrained(local_dir)` loads exactly what's
# on disk, and `local_dir` is a revision-specific path under the HF cache
# (`<HF_HOME>/hub/models--<org>--<name>/snapshots/<sha>/`).

# ====== Standard Library Imports ======
from __future__ import annotations

# ====== Third-Party Library Imports ======
from huggingface_hub import snapshot_download
from loggerplusplus import loggerplusplus


class ModelRevisionResolver:
    """
    Static helper that resolves a HuggingFace model id to a pinned local snapshot path.

    When no revision is configured, resolution is a no-op — the bare repo id is returned
    unchanged and FlagEmbedding downloads/reads whatever `main` currently points to (the
    existing floating behavior, preserved for anyone who clears the revision env vars).
    """

    logger = loggerplusplus.bind(identifier="ModelRevisionResolver")

    def __new__(cls, *args: object, **kwargs: object) -> None:  # type: ignore[misc]
        raise TypeError(
            f"ModelRevisionResolver is a static-only class and cannot be instantiated."
        )

    @classmethod
    def resolve(cls, model_id: str, revision: str | None) -> str:
        """
        Resolve a model id to a pinned local snapshot path, or pass it through unchanged.

        Args:
            model_id (str): HuggingFace repo id, e.g. "BAAI/bge-m3".
            revision (str | None): Commit sha to pin, or empty/None to keep the floating
                (main-branch) behavior.

        Returns:
            str: The local snapshot directory when `revision` is set, otherwise `model_id`
                unchanged.

        Raises:
            Exception: Whatever `huggingface_hub.snapshot_download` raises on failure (e.g. a
                network error). Deliberately NOT caught here — a pinned deploy that cannot
                fetch its pinned weights must fail loudly at startup, not silently fall back
                to the floating `main` revision.
        """
        # 1. No revision configured — unchanged floating behavior, no download call at all.
        if not revision:
            cls.logger.debug(f"No revision pinned for {model_id}; using floating 'main'.")
            return model_id

        # 2. Resolve (or reuse, if already cached) the pinned snapshot to a local directory.
        # No `allow_patterns` filter — FlagEmbedding needs the full snapshot (weights, tokenizer,
        # config) exactly as `from_pretrained(model_id)` would have pulled at that revision.
        cls.logger.info(f"Resolving pinned revision for {model_id} -> revision={revision}")
        local_path = snapshot_download(repo_id=model_id, revision=revision)
        cls.logger.info(f"Model {model_id} pinned to revision={revision} -> path={local_path}")
        return local_path
