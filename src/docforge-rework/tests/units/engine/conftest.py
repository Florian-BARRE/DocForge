# ====== Code Summary ======
# Minimal artefact + node fixtures shared by the engine test modules (ported from the
# scratchpad's test_engine_v2.py cast of characters).

# ====== Third-Party Library Imports ======
from pydantic import BaseModel  # noqa: F401 — re-exported for convenience in some tests

from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput, ScoredOutput
from shared_libs.public_models.base import Artifact


class Cfg(NodeConfig):
    pass


class Doc(Artifact):
    text: str = ""


class Empty(NodeInput):
    pass


class DocOut(NodeOutput):
    doc: Doc


class DocIn(NodeInput):
    doc: Doc


class ScoredDocOut(ScoredOutput):
    doc: Doc


class Producer(ActionNode):
    KIND = "test_engine_producer"
    NAME = "P"
    SUMMARY = "s"
    Config = Cfg
    Consumes = Empty
    Produces = DocOut

    def __init__(self, id: str, config: Cfg, text: str = "x") -> None:
        super().__init__(id, config)
        self._text = text

    async def run(self, data: Empty) -> DocOut:
        return DocOut(doc=Doc(text=self._text))


class Failer(ActionNode):
    KIND = "test_engine_failer"
    NAME = "F"
    SUMMARY = "s"
    Config = Cfg
    Consumes = Empty
    Produces = DocOut

    async def run(self, data: Empty) -> DocOut:
        raise RuntimeError("boom")


class Scorer(ActionNode):
    KIND = "test_engine_scorer"
    NAME = "Sc"
    SUMMARY = "s"
    Config = Cfg
    Consumes = Empty
    Produces = ScoredDocOut

    def __init__(self, id: str, config: Cfg, score: float) -> None:
        super().__init__(id, config)
        self._score = score

    async def run(self, data: Empty) -> ScoredDocOut:
        return ScoredDocOut(doc=Doc(text="scored"), score=self._score)


class Consumer(ActionNode):
    KIND = "test_engine_consumer"
    NAME = "C"
    SUMMARY = "s"
    Config = Cfg
    Consumes = DocIn
    Produces = DocOut

    async def run(self, data: DocIn) -> DocOut:
        return DocOut(doc=Doc(text=data.doc.text + " -> C"))


class Slow(ActionNode):
    KIND = "test_engine_slow"
    NAME = "Sl"
    SUMMARY = "s"
    Config = Cfg
    Consumes = Empty
    Produces = DocOut

    async def run(self, data: Empty) -> DocOut:
        import asyncio

        await asyncio.sleep(2)
        return DocOut(doc=Doc(text="slow"))
