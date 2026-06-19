# ====== Code Summary ======
# One-shot script: rewrites all absolute `from libs.*` import paths in the project
# after the libs/ bucket restructuring (domain-first, 6-bucket architecture).
# Run from the project root: python scripts/update_imports.py

# ====== Standard Library Imports ======
import pathlib
import re
import sys

# Ordered replacement table — most specific first to avoid double-substitution.
# Each entry: (old_prefix, new_prefix). The script replaces both:
#   from <old_prefix>.<rest> import ...
#   import <old_prefix>.<rest>
REPLACEMENTS: list[tuple[str, str]] = [
    # ── domain/ ──────────────────────────────────────────────────────────────
    ("libs.core.ir", "libs.domain.ir"),
    ("libs.core.metadata", "libs.domain.metadata"),

    # ── config/pipeline/stages/ ──────────────────────────────────────────────
    ("libs.config.pipeline.parse_config", "libs.config.pipeline.stages.parse_config"),
    ("libs.config.pipeline.enrich_config", "libs.config.pipeline.stages.enrich_config"),
    ("libs.config.pipeline.chunk_config", "libs.config.pipeline.stages.chunk_config"),
    ("libs.config.pipeline.contextualize_config", "libs.config.pipeline.stages.contextualize_config"),
    ("libs.config.pipeline.embed_config", "libs.config.pipeline.stages.embed_config"),
    ("libs.config.pipeline.heading_rule", "libs.config.pipeline.stages.heading_rule"),
    ("libs.config.pipeline.pipeline_config", "libs.config.pipeline"),

    # ── config/pipeline/ ─────────────────────────────────────────────────────
    ("libs.config.pipeline._registry", "libs.config.pipeline._registry"),
    ("libs.config.pipeline.spec_utils", "libs.config.pipeline.spec_utils"),
    ("libs.config.pipeline.chain_gate_config", "libs.config.pipeline.chain_gate_config"),
    ("libs.core.contracts", "libs.config.pipeline"),

    # ── config/validation + config/admission ─────────────────────────────────
    ("libs.config.config_validation", "libs.config.validation"),
    ("libs.config.admission", "libs.config.admission"),
    ("libs.governance", "libs.config"),

    # ── providers/ ───────────────────────────────────────────────────────────
    ("libs.capabilities", "libs.providers"),

    # ── storage/ ─────────────────────────────────────────────────────────────
    ("libs.data.storage", "libs.storage"),

    # ── search/ ──────────────────────────────────────────────────────────────
    ("libs.search.field_index", "libs.search.field_index"),
    ("libs.search.hybrid_search_helpers", "libs.search.hybrid.helpers"),
    ("libs.search.hybrid_search_models", "libs.search.hybrid.models"),
    ("libs.search.hybrid_search", "libs.search.hybrid.service"),
    ("libs.search.metadata_indexer_helpers", "libs.search.metadata_indexer.helpers"),
    ("libs.search.metadata_indexer", "libs.search.metadata_indexer.indexer"),
    ("libs.data.retrieval", "libs.search"),

    # ── pipeline/caches/ ─────────────────────────────────────────────────────
    ("libs.pipeline.fingerprint", "libs.pipeline.caches.fingerprint"),
    ("libs.pipeline.node_cache_ops", "libs.pipeline.caches.node_cache_ops"),
    ("libs.pipeline.node_cache", "libs.pipeline.caches.node_cache"),
    ("libs.pipeline.provider_cache", "libs.pipeline.caches.provider_cache"),

    # ── pipeline/worker/ ─────────────────────────────────────────────────────
    ("libs.pipeline.runner", "libs.pipeline.worker.runner"),
    ("libs.pipeline.worker_bootstrap", "libs.pipeline.worker.worker_bootstrap"),
    ("libs.pipeline.worker", "libs.pipeline.worker.worker"),
    ("libs.pipeline.tasks", "libs.pipeline.worker.tasks"),

    # ── pipeline/stages/s4_chunk internals ───────────────────────────────────
    ("libs.pipeline.stages.s4_chunk.base_splitter", "libs.pipeline.stages.s4_chunk.strategies.base"),
    ("libs.pipeline.stages.s4_chunk.semantic_splitter", "libs.pipeline.stages.s4_chunk.strategies.semantic"),
    ("libs.pipeline.stages.s4_chunk.token_budget_splitter", "libs.pipeline.stages.s4_chunk.strategies.token_budget"),
    ("libs.pipeline.stages.s4_chunk.sentence_window_splitter", "libs.pipeline.stages.s4_chunk.strategies.sentence_window"),
    ("libs.pipeline.stages.s4_chunk.params", "libs.pipeline.stages.s4_chunk.strategies.params"),
    ("libs.pipeline.stages.s4_chunk.semantic_config", "libs.pipeline.stages.s4_chunk.config.semantic"),
    ("libs.pipeline.stages.s4_chunk.token_budget_config", "libs.pipeline.stages.s4_chunk.config.token_budget"),
    ("libs.pipeline.stages.s4_chunk.sentence_window_config", "libs.pipeline.stages.s4_chunk.config.sentence_window"),
    ("libs.pipeline.stages.s4_chunk.helpers", "libs.pipeline.stages.s4_chunk.helpers.text"),
    ("libs.pipeline.stages.s4_chunk.cross_reference_linker", "libs.pipeline.stages.s4_chunk.helpers.linker"),
    ("libs.pipeline.stages.chunking", "libs.pipeline.stages.s4_chunk"),

    # ── pipeline/stages/s4_chunk assemblers ──────────────────────────────────
    ("libs.pipeline.stages.s4_chunk.chunk_assembler_flat", "libs.pipeline.stages.s4_chunk.assemblers.flat"),
    ("libs.pipeline.stages.s4_chunk.chunk_assembler_hier", "libs.pipeline.stages.s4_chunk.assemblers.hierarchical"),
    ("libs.pipeline.stages.s4_chunk.chunk_assembler", "libs.pipeline.stages.s4_chunk.assemblers.base"),

    # ── pipeline/stages/ (flat stage files → core.py) ────────────────────────
    ("libs.pipeline.stages.s0_ingest", "libs.pipeline.stages.s0_ingest.core"),
    ("libs.pipeline.stages.s1_parse", "libs.pipeline.stages.s1_parse.core"),
    ("libs.pipeline.stages.s5_contextualize", "libs.pipeline.stages.s5_contextualize.core"),
    ("libs.pipeline.stages.s6_embed_index", "libs.pipeline.stages.s6_embed_index.core"),

    # ── pipeline/ catch-alls (must be last) ──────────────────────────────────
    ("libs.pipeline.stages", "libs.pipeline.stages"),
    ("libs.pipeline.engine", "libs.pipeline.engine"),
    ("libs.engine", "libs.pipeline"),
]

# Directories to skip entirely.
SKIP_DIRS = {".git", "__pycache__", ".venv", "node_modules", ".mypy_cache", ".ruff_cache"}

# File extensions to process.
TARGET_EXTS = {".py"}


def _build_pattern(old: str) -> re.Pattern:
    """
    Build a regex that matches the old import prefix only as a complete module token.

    Matches:
        from <old>.<rest> import ...
        from <old> import ...
        import <old>.<rest>
        import <old>
    """
    escaped = re.escape(old)
    # After the prefix, we accept either end-of-token (space, newline, comma) or a dot.
    return re.compile(r"(?<![.\w])" + escaped + r"(?=\.|\s|,|$)", re.MULTILINE)


def process_file(path: pathlib.Path, dry_run: bool = False) -> int:
    """
    Apply all replacements to a single file.

    Args:
        path (pathlib.Path): File to process.
        dry_run (bool): If True, report changes without writing.

    Returns:
        int: Number of replacements made.
    """
    # 1. Read original content
    original = path.read_text(encoding="utf-8", errors="replace")
    content = original

    # 2. Apply replacements in order (most specific first)
    for old, new in REPLACEMENTS:
        pattern = _build_pattern(old)
        content, _ = pattern.subn(new, content)

    # 3. Write back only if changed
    if content == original:
        return 0

    count = sum(
        len(_build_pattern(old).findall(original))
        for old, _ in REPLACEMENTS
        if old in original
    )
    if not dry_run:
        path.write_text(content, encoding="utf-8")
    print(f"  {'[DRY]' if dry_run else '[MOD]'} {path}  ({count} replacement(s))")
    return 1


def collect_files(root: pathlib.Path) -> list[pathlib.Path]:
    """
    Recursively collect all .py files under root, skipping excluded directories.

    Args:
        root (pathlib.Path): Repository root to walk.

    Returns:
        list[pathlib.Path]: Sorted list of Python file paths.
    """
    result: list[pathlib.Path] = []
    for item in root.rglob("*"):
        if any(part in SKIP_DIRS for part in item.parts):
            continue
        if item.suffix in TARGET_EXTS and item.is_file():
            result.append(item)
    return sorted(result)


def main() -> None:
    """
    Entry point — walk project tree and rewrite all import paths.
    """
    # 1. Locate project root (directory containing this script's parent)
    root = pathlib.Path(__file__).resolve().parent.parent

    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print(f"DRY RUN — no files will be written\n")

    print(f"Scanning {root} ...\n")

    # 2. Collect all Python files
    files = collect_files(root)

    # 3. Process each file
    modified = 0
    for f in files:
        modified += process_file(f, dry_run=dry_run)

    # 4. Report summary
    print(f"\nDone. {modified}/{len(files)} files updated.")


if __name__ == "__main__":
    main()
