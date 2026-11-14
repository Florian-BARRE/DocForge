"""TraceCapture: one payload side captured at the engine's trace level (off / shape / full)."""

from shared_libs.pipelines.engine import TraceLevel
from shared_libs.pipelines.engine.trace_capture import TraceCapture

from .conftest import Doc, DocOut


def test_none_payload_captures_nothing_at_every_level() -> None:
    for level in TraceLevel:
        assert TraceCapture(level).capture(None) == (None, None)


def test_off_captures_nothing() -> None:
    assert TraceCapture(TraceLevel.OFF).capture(DocOut(doc=Doc(text="x"))) == (None, None)


def test_shape_captures_only_the_summary() -> None:
    full, summary = TraceCapture(TraceLevel.SHAPE).capture(DocOut(doc=Doc(text="x")))
    assert full is None
    assert summary is not None


def test_full_captures_summary_and_dump() -> None:
    full, summary = TraceCapture(TraceLevel.FULL).capture(DocOut(doc=Doc(text="x")))
    assert full is not None
    assert summary is not None
