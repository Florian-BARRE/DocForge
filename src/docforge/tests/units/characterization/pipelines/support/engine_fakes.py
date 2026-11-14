# ====== Code Summary ======
# Fake artefacts and fake action nodes of the engine characterization suite. They are tiny, pure and
# deterministic (no I/O): each fake does one visible thing so a record sequence says which branch of the
# engine ran. They mirror the cast of tests/units/engine/conftest.py (that module is a conftest of a
# sibling folder, not importable from here) and add the fakes the error branches need.

# ====== Standard Library Imports ======
import asyncio

# ====== Internal Project Imports ======
from shared_libs.pipelines.base import ActionNode, NodeConfig, NodeInput, NodeOutput, ScoredOutput
from shared_libs.public_models.base import Artifact


class FakeConfig(NodeConfig):
    """The empty config every fake node shares."""


class Doc(Artifact):
    """The artefact the fakes pass along."""

    text: str = ""


class EmptyIn(NodeInput):
    """A node input with no slot."""


class DocIn(NodeInput):
    """A node input with one required ``doc`` slot."""

    doc: Doc


class ItemIn(NodeInput):
    """A node input with one required ``item`` slot (what a ForEach body reads from its group input)."""

    item: Doc


class DocOut(NodeOutput):
    """A node output with one ``doc`` slot."""

    doc: Doc


class ScoredDocOut(ScoredOutput):
    """A scored output with a ``doc`` slot (a ScoreBelow edge reads its score)."""

    doc: Doc


class DocsOut(NodeOutput):
    """A node output carrying a list of docs and a scalar note (to bind a non-list to ``over``)."""

    docs: list[Doc]
    note: str = "not-a-list"


class EntryOut(NodeOutput):
    """A single-slot Artifact output: a valid terminal of a ForEach body."""

    entry: Doc


class OtherOut(NodeOutput):
    """A single-slot output of ANOTHER artefact type: breaks a ForEach body's uniform terminal."""

    other: Artifact


class TwoSlotOut(NodeOutput):
    """A two-slot output: an invalid ForEach body terminal (not a single collectable slot)."""

    first: Doc
    second: Doc


class Producer(ActionNode):
    """Produces a ``Doc`` with the configured text."""

    KIND = "charact_producer"
    NAME = "Producer"
    SUMMARY = "Produces a doc."
    Config = FakeConfig
    Consumes = EmptyIn
    Produces = DocOut

    def __init__(self, id: str, text: str = "x") -> None:
        super().__init__(id, FakeConfig())
        self._text = text

    async def run(self, data: EmptyIn) -> DocOut:
        return DocOut(doc=Doc(text=self._text))


class CacheableProducer(Producer):
    """A producer that declares itself cacheable and counts its runs (a cache HIT must skip it)."""

    KIND = "charact_cacheable_producer"
    CACHEABLE = True
    CACHE_VERSION = "1"

    def __init__(self, id: str, text: str = "x") -> None:
        super().__init__(id, text)
        self.run_count = 0

    async def run(self, data: EmptyIn) -> DocOut:
        self.run_count += 1
        return await super().run(data)


class Failer(ActionNode):
    """Always raises ``RuntimeError("boom")``."""

    KIND = "charact_failer"
    NAME = "Failer"
    SUMMARY = "Always fails."
    Config = FakeConfig
    Consumes = EmptyIn
    Produces = DocOut

    def __init__(self, id: str) -> None:
        super().__init__(id, FakeConfig())

    async def run(self, data: EmptyIn) -> DocOut:
        raise RuntimeError("boom")


class Scorer(ActionNode):
    """Produces a scored doc with a fixed score."""

    KIND = "charact_scorer"
    NAME = "Scorer"
    SUMMARY = "Produces a scored doc."
    Config = FakeConfig
    Consumes = EmptyIn
    Produces = ScoredDocOut

    def __init__(self, id: str, score: float) -> None:
        super().__init__(id, FakeConfig())
        self._score = score

    async def run(self, data: EmptyIn) -> ScoredDocOut:
        return ScoredDocOut(doc=Doc(text="scored"), score=self._score)


class Consumer(ActionNode):
    """Appends ``" -> C"`` to the doc it consumes."""

    KIND = "charact_consumer"
    NAME = "Consumer"
    SUMMARY = "Consumes a doc."
    Config = FakeConfig
    Consumes = DocIn
    Produces = DocOut

    def __init__(self, id: str) -> None:
        super().__init__(id, FakeConfig())

    async def run(self, data: DocIn) -> DocOut:
        return DocOut(doc=Doc(text=f"{data.doc.text} -> C"))


class Sleeper(ActionNode):
    """Sleeps far longer than any test deadline."""

    KIND = "charact_sleeper"
    NAME = "Sleeper"
    SUMMARY = "Sleeps."
    Config = FakeConfig
    Consumes = EmptyIn
    Produces = DocOut

    def __init__(self, id: str) -> None:
        super().__init__(id, FakeConfig())

    async def run(self, data: EmptyIn) -> DocOut:
        await asyncio.sleep(30)
        return DocOut(doc=Doc(text="never"))


class DocsProducer(ActionNode):
    """Produces a list of docs (the list a ForEach iterates) and a scalar note."""

    KIND = "charact_docs_producer"
    NAME = "DocsProducer"
    SUMMARY = "Produces a list of docs."
    Config = FakeConfig
    Consumes = EmptyIn
    Produces = DocsOut

    def __init__(self, id: str, texts: list[str]) -> None:
        super().__init__(id, FakeConfig())
        self._texts = texts

    async def run(self, data: EmptyIn) -> DocsOut:
        return DocsOut(docs=[Doc(text=text) for text in self._texts])


class ItemEcho(ActionNode):
    """A ForEach body leaf: turns the item into an ``entry`` (raises on the item text ``"boom"``)."""

    KIND = "charact_item_echo"
    NAME = "ItemEcho"
    SUMMARY = "Echoes an item."
    Config = FakeConfig
    Consumes = ItemIn
    Produces = EntryOut

    def __init__(self, id: str) -> None:
        super().__init__(id, FakeConfig())

    async def run(self, data: ItemIn) -> EntryOut:
        if data.item.text == "boom":
            raise RuntimeError("item exploded")
        return EntryOut(entry=Doc(text=f"echo:{data.item.text}"))


class ItemOther(ActionNode):
    """A ForEach body leaf producing ANOTHER artefact type than ``ItemEcho``."""

    KIND = "charact_item_other"
    NAME = "ItemOther"
    SUMMARY = "Produces another artefact."
    Config = FakeConfig
    Consumes = ItemIn
    Produces = OtherOut

    def __init__(self, id: str) -> None:
        super().__init__(id, FakeConfig())

    async def run(self, data: ItemIn) -> OtherOut:
        return OtherOut(other=Artifact())


class ItemTwoSlots(ActionNode):
    """A ForEach body leaf with a two-slot output: it violates the collection contract."""

    KIND = "charact_item_two_slots"
    NAME = "ItemTwoSlots"
    SUMMARY = "Produces two slots."
    Config = FakeConfig
    Consumes = ItemIn
    Produces = TwoSlotOut

    def __init__(self, id: str) -> None:
        super().__init__(id, FakeConfig())

    async def run(self, data: ItemIn) -> TwoSlotOut:
        return TwoSlotOut(first=Doc(), second=Doc())
