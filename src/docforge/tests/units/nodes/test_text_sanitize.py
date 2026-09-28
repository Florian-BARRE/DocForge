# ====== Code Summary ======
# Guards for the NUL (U+0000) sanitization that fixes the prod crash where a NUL in extracted PDF text
# reached a Postgres text/jsonb column and killed the job (asyncpg UntranslatableCharacterError). Two
# layers: the pure recursive TextSanitizer.strip_nul (the DB-edge net the translator applies to every
# value it writes) and the IrTextSanitizer.clean post-parse chokepoint over a DocumentIR.

# ====== Standard Library Imports ======
# (none)

# ====== Internal Project Imports ======
from shared_libs.public_models import DocumentIR, IrTextSanitizer, Provenance, TextSanitizer
from shared_libs.public_models.ir import Block, BlockType
from shared_libs.public_models.ir.figure import FigureEnrichment
from shared_libs.public_models.ir.table import TableData


def test_strip_nul_scalar_string() -> None:
    assert TextSanitizer.strip_nul("a\x00b\x00c") == "abc"
    # A string with no NUL is returned unchanged (identity fast-path).
    clean = "no nul here"
    assert TextSanitizer.strip_nul(clean) is clean


def test_strip_nul_prod_shape_json_list() -> None:
    # The exact prod shape: a JSONB value that is a list of generated statements, one with a NUL.
    value = ["L’AFD est un établissement.", "service\x00 fait."]
    assert TextSanitizer.strip_nul(value) == ["L’AFD est un établissement.", "service fait."]


def test_strip_nul_recurses_dict_keys_and_tuples() -> None:
    src = {"k\x00ey": ["x\x00", ("y\x00", 3)], "n": 42}
    assert TextSanitizer.strip_nul(src) == {"key": ["x", ("y", 3)], "n": 42}


def test_strip_nul_leaves_non_strings_untouched() -> None:
    assert TextSanitizer.strip_nul(7) == 7
    assert TextSanitizer.strip_nul(None) is None
    assert TextSanitizer.strip_nul(True) is True


def _block(block_id: str, block_type: BlockType, order: int, **kw) -> Block:
    return Block(
        id=block_id,
        block_type=block_type,
        provenance=Provenance(page=0, bbox=(0.0, 0.0, 1.0, 1.0)),
        reading_order=order,
        **kw,
    )


def test_ir_sanitizer_cleans_every_text_field() -> None:
    ir = DocumentIR(
        doc_id="doc-1",
        source_hash="hash-1",
        title="Titre\x00 AFD",
        blocks=[
            _block("b0", BlockType.PARAGRAPH, 0, text="para\x00graphe"),
            _block(
                "b1",
                BlockType.TABLE,
                1,
                table=TableData(cells=[["a\x00", "b"], ["c", "d\x00"]], n_rows=2, n_cols=2),
            ),
            _block(
                "b2",
                BlockType.FIGURE,
                2,
                figure=FigureEnrichment(
                    ocr_text="ocr\x00", description="desc\x00", data_table=[["x\x00", "y"]]
                ),
            ),
        ],
    )

    cleaned = IrTextSanitizer.clean(ir)

    assert cleaned.title == "Titre AFD"
    assert cleaned.blocks[0].text == "paragraphe"
    assert cleaned.blocks[1].table.cells == [["a", "b"], ["c", "d"]]
    assert cleaned.blocks[2].figure.ocr_text == "ocr"
    assert cleaned.blocks[2].figure.description == "desc"
    assert cleaned.blocks[2].figure.data_table == [["x", "y"]]
