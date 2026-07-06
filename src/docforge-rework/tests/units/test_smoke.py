"""Smoke test: the bootstrap resolves shared_libs, worker libs and the app import root."""


def test_shared_libs_importable() -> None:
    from shared_libs.pipelines.base import Group  # noqa: F401


def test_worker_libs_importable() -> None:
    from persistence import RunTranslator  # noqa: F401
    from runner import PipelineRunner  # noqa: F401


def test_registry_populated() -> None:
    from shared_libs.pipelines.registry import NodeRegistry

    assert "chunker" in NodeRegistry.families()
    assert {"structure_aware", "fixed_size", "semantic"} <= set(NodeRegistry.kinds("chunker"))
