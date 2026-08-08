# ====== Code Summary ======
# Pinned dependency versions for the PP-StructureV3 stack — a supply-chain / reproducibility
# reference, NOT enforced at runtime (the actual pins live in pyproject.toml / uv.lock; this
# module only documents them for the /health + /layout-parsing "engine" block so a caller can
# see exactly what produced a given response). Update in lockstep with pyproject.toml whenever
# the pins change.
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
