# ====== Code Summary ======
# Documentation-only record of the pinned PP-StructureV3 stack versions — the single place the
# normalizers cross-reference ("see revision.py") for WHY the pins are exact. It is NOT consumed at
# runtime and NOT re-exported from the package: the actual pins are enforced by pyproject.toml /
# uv.lock, and the /layout-parsing "engine" block reports the ACTUALLY-installed paddleocr version
# (PpStructureService._paddleocr_version), which is more truthful than a hand-maintained constant
# that could silently drift from what is installed. Keep this dict in lockstep with pyproject.toml.
#
# WHY pinned exact (not floating): the `parsing_res_list` schema drifted between PaddleOCR
# release/3.0 (nested `{layout_bbox, "{label}": content}`) and >=3.1 (flat `{block_label,
# block_content, block_bbox}` — verified against the paddleocr==3.7.0 / paddlex==3.7.0 wheel
# source, see libs/ppstructure/normalizer.py). An un-gated upgrade could silently change what
# this sidecar returns.

PADDLE_PIN_INFO: dict[str, str] = {
    "paddleocr": "3.7.0",
    "paddlex": "3.7.0",
    "paddlepaddle": "3.3.1",
}
