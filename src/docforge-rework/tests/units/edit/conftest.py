# ====== Code Summary ======
# Shared helpers for the edit-operation tests: a build+validate shortcut and the default blob.

# ====== Third-Party Library Imports ======
import pytest

from shared_libs.pipelines.build.blob import GroupNodeBlob
from shared_libs.pipelines.ingest import IngestPipeline


def issues_of(builder, validator, blob: GroupNodeBlob) -> list:
    """Build + validate a blob, returning its validation issues."""
    return validator.validate(builder.build(blob))


@pytest.fixture
def default_blob() -> GroupNodeBlob:
    """A fresh copy of the stock ingestion blob (7 stages, all wired)."""
    return IngestPipeline.default_blob()
