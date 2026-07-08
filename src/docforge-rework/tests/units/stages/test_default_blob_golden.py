"""Frozen golden of the stock ingestion blob — locks the default topology byte-for-byte.

The "byte-identical default" guarantee that lets every phase evolve the pipeline without silently
drifting the stock blob is pinned HERE: a single checked-in snapshot of
``IngestAssembler.assemble(default_state()).model_dump(mode="json")``. If a change to the assembler,
the state defaults or any stage builder alters the default blob, this test fails loudly and the
snapshot must be regenerated ON PURPOSE (never blindly). To regenerate after an intended change:
``fixtures/default_blob.json`` = json.dumps(blob.model_dump(mode="json"), sort_keys=True, indent=2)
(pretty-printed so its diff stays readable — the test compares dicts, so the layout is cosmetic).
"""

import json
import pathlib

from shared_libs.pipelines.ingest.stages import IngestAssembler, default_state

_GOLDEN = pathlib.Path(__file__).parent / "fixtures" / "default_blob.json"


def test_default_blob_matches_the_frozen_golden() -> None:
    expected = json.loads(_GOLDEN.read_text())
    actual = IngestAssembler.assemble(default_state()).model_dump(mode="json")
    assert actual == expected
