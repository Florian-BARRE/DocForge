# ====== Code Summary ======
# Shared helpers for the edit-operation tests: a build+validate shortcut and the default blob.

# ====== Third-Party Library Imports ======
import pytest

from shared_libs.pipelines.build.blob import GroupNodeBlob
from shared_libs.pipelines.ingest import IngestPipeline
from shared_libs.pipelines.ingest.stages import EnableStage, StageCompiler


def issues_of(builder, validator, blob: GroupNodeBlob) -> list:
    """Build + validate a blob, returning its validation issues."""
    return validator.validate(builder.build(blob))


@pytest.fixture
def default_blob() -> GroupNodeBlob:
    """A fresh copy of the stock ingestion blob (provider-hosted stages OFF by default)."""
    return IngestPipeline.default_blob()


@pytest.fixture
def full_blob() -> GroupNodeBlob:
    """The stock blob with every provider-hosted stage (enrich + both metagen scopes) enabled — the
    fully-wired topology whose per-figure / metagen nodes the edit-mechanics tests operate on."""
    compiler = StageCompiler()
    blob = IngestPipeline.default_blob()
    for stage in ("enrich", "metagen_chunk", "metagen_document"):
        blob, _ = compiler.apply(blob, EnableStage(stage=stage))
    return blob
