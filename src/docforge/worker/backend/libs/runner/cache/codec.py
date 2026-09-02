# ====== Code Summary ======
# ArtifactCodec — the (de)serialisation + content-hash primitive the stage cache stores through. A
# node's Produces/Consumes model is dumped to a plain python tree (mode="python", so BYTES stay raw
# — an IR figure crop is binary) and packed with msgpack (bin-safe, compact, deterministic key order
# from the model's field order). Round-tripping back into the declared model re-validates the tree,
# so a served artefact is byte-identical to a freshly-produced one. sha256 over the packed frame is
# the content hash used as the S3 key and the input fingerprint.

# ====== Standard Library Imports ======
import hashlib
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

# ====== Third-Party Library Imports ======
import msgpack
from pydantic import BaseModel


class ArtifactCodec:
    """Static msgpack (de)serialisation + sha256 for pipeline artefact models."""

    logger = None  # static-only; no instance logger needed

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ArtifactCodec is a static-only class and cannot be instantiated.")

    @staticmethod
    def __encode(obj: Any) -> Any:
        """msgpack fallback for the few non-primitive leaves a model_dump(python) can still hold."""
        # StrEnum is already a str (handled natively); this covers non-str enums, UUID and datetime.
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Cannot serialise object of type {type(obj).__name__} for the cache")

    @classmethod
    def pack(cls, model: BaseModel) -> bytes:
        """Serialise a pydantic model to a deterministic, bytes-safe msgpack frame."""
        tree = model.model_dump(mode="python")
        return msgpack.packb(tree, default=cls.__encode, use_bin_type=True)

    @staticmethod
    def unpack(data: bytes, model_type: type[BaseModel]) -> BaseModel:
        """Deserialise a msgpack frame back into (and re-validate as) the declared model type."""
        tree = msgpack.unpackb(data, raw=False)
        return model_type.model_validate(tree)

    @staticmethod
    def sha256(data: bytes) -> str:
        """The content hash of a serialised frame (the S3 key / blob content_hash)."""
        return hashlib.sha256(data).hexdigest()


__all__ = ["ArtifactCodec"]
