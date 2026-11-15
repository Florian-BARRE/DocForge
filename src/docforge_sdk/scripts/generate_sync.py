# ====== Code Summary ======
# Codegen that DERIVES the synchronous SDK modules from their asynchronous twins (unasync-style). The
# async module is the single hand-written source of truth; the committed ``sync_*.py`` files are its
# mechanical transform: ``async def`` / ``await`` / ``async for`` / ``async with`` dropped, ``AsyncX``
# names renamed ``SyncX``, then the output is import-sorted and formatted by the project's own ruff, so
# the generated files are ordinary typed modules (``mypy --strict`` and ``inspect.signature`` see real
# code, nothing is patched at runtime).
#
# Run from ``src/docforge_sdk``:
#   uv run --frozen python scripts/generate_sync.py          # rewrite the sync files
#   uv run --frozen python scripts/generate_sync.py --check  # exit 1 when a committed file drifted
# ``tests/unit/test_sync_codegen.py`` asserts the committed files equal the generator output.

# ====== Standard Library Imports ======
import argparse
import io
import re
import subprocess
import sys
import tokenize
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

# The SDK project root (the directory holding ``pyproject.toml``) and its package.
SDK_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = SDK_ROOT / "docforge_sdk"

_GENERATED_NOTICE = (
    "GENERATED FILE — DO NOT EDIT. Derived from {source} by scripts/generate_sync.py;",
    "regenerate with `uv run --frozen python scripts/generate_sync.py` from src/docforge_sdk",
    "(tests/unit/test_sync_codegen.py fails when this file drifts from its async source).",
)


@dataclass(frozen=True)
class Target:
    """
    One async module and the sync module derived from it.

    Attributes:
        source (Path): The hand-written async module.
        output (Path): The generated sync module.
        prose_rules (tuple[tuple[str, str], ...]): ``(regex, replacement)`` pairs applied to the
            docstrings and comments of the transport pair, where "async" is a technical word. Resource
            docstrings are left untouched: their "asynchronous" describes the SERVER (queued jobs).
    """

    source: Path
    output: Path
    prose_rules: tuple[tuple[str, str], ...] = field(default=())


class SyncTransformer:
    """Pure async-to-sync source transform: no file access, no formatting."""

    # Exact renames, tried before the generic ``AsyncX`` -> ``SyncX`` rule.
    _NAME_RULES = {
        "AsyncIterator": "Iterator",
        "AsyncClient": "Client",
        "aclose": "close",
        "aiter_bytes": "iter_bytes",
        "aread": "read",
    }
    _ASYNC_PREFIX = re.compile(r"^Async(?=[A-Z])")
    _QUOTED_ASYNC_NAME = re.compile(r"""^(['"])Async([A-Z]\w*)\1$""")
    # Keywords that, once ``async`` is dropped, leave a plain statement.
    _ASYNC_COMPANIONS = {"def", "for", "with"}
    _HEADER_RULES = (
        (re.compile(r"\bAsynchronous\b"), "Synchronous"),
        (re.compile(r"\basynchronous\b"), "synchronous"),
        (re.compile(r"\bawaiting\b"), "blocking"),
        (re.compile(r"\basync\b"), "sync"),
        (re.compile(r"httpx\.AsyncClient"), "httpx.Client"),
    )
    _CLASS_DOC = re.compile(r'(?m)^(class \w+(?:\([^)]*\))?:\n    """)Asynchronous\b')
    _SUMMARY_BANNER = "# ====== Code Summary ======"

    def transform(
        self, source: str, source_name: str, prose_rules: Sequence[tuple[str, str]]
    ) -> str:
        """
        Derive the sync module text from an async module's text.

        Args:
            source (str): The async module source.
            source_name (str): The async file name, quoted in the generated notice.
            prose_rules (Sequence[tuple[str, str]]): Extra ``(regex, replacement)`` prose rewrites.

        Returns:
            str: The (not yet formatted) sync module source.
        """
        code = self._rewrite_tokens(source)
        code = self._CLASS_DOC.sub(r"\1Synchronous", code)
        for pattern, replacement in prose_rules:
            code = re.sub(pattern, replacement, code)
        return self._rewrite_header(code, source_name)

    def _rewrite_tokens(self, source: str) -> str:
        """Drop ``async``/``await`` and rename ``AsyncX`` identifiers, touching code tokens only."""
        offsets = [0]
        for line in source.splitlines(keepends=True):
            offsets.append(offsets[-1] + len(line))
        tokens = [
            tok
            for tok in tokenize.generate_tokens(io.StringIO(source).readline)
            if tok.type not in (tokenize.NL, tokenize.COMMENT)
        ]
        edits: list[tuple[int, int, str]] = []
        for index, tok in enumerate(tokens):
            if tok.type == tokenize.STRING and self._QUOTED_ASYNC_NAME.match(tok.string):
                # ``__all__`` entries and forward references name the class as a string.
                quoted = self._QUOTED_ASYNC_NAME.sub(r"\1Sync\2\1", tok.string)
                start = offsets[tok.start[0] - 1] + tok.start[1]
                edits.append((start, offsets[tok.end[0] - 1] + tok.end[1], quoted))
                continue
            if tok.type != tokenize.NAME:
                continue
            start = offsets[tok.start[0] - 1] + tok.start[1]
            end = offsets[tok.end[0] - 1] + tok.end[1]
            following = tokens[index + 1]
            glued_end = offsets[following.start[0] - 1] + following.start[1]
            if tok.string == "await" or (
                tok.string == "async" and following.string in self._ASYNC_COMPANIONS
            ):
                edits.append((start, glued_end, ""))
            elif tok.string in self._NAME_RULES:
                edits.append((start, end, self._NAME_RULES[tok.string]))
            elif self._ASYNC_PREFIX.match(tok.string):
                edits.append((start, end, self._ASYNC_PREFIX.sub("Sync", tok.string)))
        for start, end, replacement in sorted(edits, reverse=True):
            source = source[:start] + replacement + source[end:]
        return source

    def _rewrite_header(self, code: str, source_name: str) -> str:
        """Swap the Code Summary block for its sync wording, headed by the GENERATED notice."""
        lines = code.splitlines(keepends=True)
        if not lines or lines[0].rstrip() != self._SUMMARY_BANNER:
            raise ValueError(f"{source_name} must open with the '{self._SUMMARY_BANNER}' block")
        end = 1
        while end < len(lines) and lines[end].startswith("#"):
            end += 1
        summary = "".join(lines[1:end])
        for pattern, replacement in self._HEADER_RULES:
            summary = pattern.sub(replacement, summary)
        notice = "".join(f"# {line.format(source=source_name)}\n" for line in _GENERATED_NOTICE)
        return f"{lines[0]}{notice}{summary}{''.join(lines[end:])}"


class RuffPipeline:
    """Runs the project's own ruff (import sort, safe fixes, formatter) over generated text."""

    # Unsafe fixes are needed for UP028 (``for x in it: yield x`` -> ``yield from it``), which the
    # dropped ``async for`` turns the async stream loops into.
    _FIX_RULES = "I,UP,F401"

    def __init__(self, project_root: Path) -> None:
        """
        Args:
            project_root (Path): The directory whose ``pyproject.toml`` configures ruff.
        """
        self._root = project_root

    def apply(self, text: str, path: Path) -> str:
        """
        Fix then format ``text`` as if it lived at ``path``.

        Args:
            text (str): Python source.
            path (Path): The file the text is destined to, so ruff resolves the right config.

        Returns:
            str: The fixed and formatted source.
        """
        fixed = self._run(
            ["check", "--fix-only", "--unsafe-fixes", "--select", self._FIX_RULES], text, path
        )
        return self._run(["format"], fixed, path)

    def _run(self, args: list[str], text: str, path: Path) -> str:
        """Run one ruff sub-command on stdin, failing loudly on any error."""
        # An explicit --config keeps the output independent of where ``path`` lives on disk.
        config = ["--config", str(self._root / "pyproject.toml")]
        command = [
            sys.executable,
            "-m",
            "ruff",
            *args,
            *config,
            "--quiet",
            "--stdin-filename",
            str(path),
            "-",
        ]
        done = subprocess.run(
            command, input=text, capture_output=True, text=True, cwd=self._root, check=False
        )
        if done.returncode != 0:
            raise RuntimeError(f"ruff {args[0]} failed for {path}: {done.stderr or done.stdout}")
        return done.stdout


class SyncCodegen:
    """Discovers the async modules, renders their sync twins and writes or checks them."""

    _TRANSPORT_PROSE = ((r"\basync\b", "sync"), (r"httpx\.AsyncClient", "httpx.Client"))

    def __init__(self, package_root: Path = PACKAGE_ROOT, project_root: Path = SDK_ROOT) -> None:
        """
        Args:
            package_root (Path): The ``docforge_sdk`` package directory.
            project_root (Path): The SDK project directory (ruff configuration lives there).
        """
        self._package = package_root
        self._transformer = SyncTransformer()
        self._ruff = RuffPipeline(project_root)

    def targets(self) -> list[Target]:
        """
        List every (async source, sync output) pair: the transport and each resource package.

        Returns:
            list[Target]: The pairs, in a stable order.
        """
        found = [
            Target(
                self._package / "_transport_async.py",
                self._package / "_transport_sync.py",
                self._TRANSPORT_PROSE,
            )
        ]
        for source in sorted((self._package / "resources").glob("*/async_*.py")):
            found.append(Target(source, source.with_name("sync_" + source.name[len("async_") :])))
        return found

    def render(self, target: Target) -> str:
        """
        Produce the exact text the sync file must hold.

        Args:
            target (Target): The pair to derive.

        Returns:
            str: The formatted sync module source.
        """
        derived = self._transformer.transform(
            target.source.read_text(encoding="utf-8"), target.source.name, target.prose_rules
        )
        return self._ruff.apply(derived, target.output)

    def drifted(self) -> list[Path]:
        """
        List the committed sync files that differ from the generator output.

        Returns:
            list[Path]: The outputs that are missing or stale.
        """
        stale: list[Path] = []
        for target in self.targets():
            expected = self.render(target)
            current = target.output.read_text(encoding="utf-8") if target.output.exists() else None
            if current != expected:
                stale.append(target.output)
        return stale

    def write(self) -> list[Path]:
        """
        Rewrite every sync file whose content changed.

        Returns:
            list[Path]: The files that were written.
        """
        written: list[Path] = []
        for target in self.targets():
            expected = self.render(target)
            if not target.output.exists() or target.output.read_text(encoding="utf-8") != expected:
                target.output.write_text(expected, encoding="utf-8")
                written.append(target.output)
        return written


def main(argv: Sequence[str] | None = None) -> int:
    """
    Command-line entry: regenerate the sync modules, or ``--check`` that they are current.

    Args:
        argv (Sequence[str] | None): Arguments (defaults to ``sys.argv[1:]``).

    Returns:
        int: ``0`` when current or rewritten, ``1`` when ``--check`` found drift.
    """
    parser = argparse.ArgumentParser(description="Derive the sync SDK modules from the async ones.")
    parser.add_argument("--check", action="store_true", help="fail when a sync file is stale")
    args = parser.parse_args(argv)
    codegen = SyncCodegen()
    if args.check:
        stale = codegen.drifted()
        for path in stale:
            print(f"stale: {path.relative_to(SDK_ROOT)}")
        return 1 if stale else 0
    for path in codegen.write():
        print(f"wrote: {path.relative_to(SDK_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
