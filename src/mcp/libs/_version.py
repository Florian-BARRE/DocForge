# ====== Code Summary ======
# The docforge release this MCP server ships with, reported as `serverInfo.version`. Lockstep
# with src/mcp/pyproject.toml, src/docforge and the SDK: moved by scripts/set_version.sh only and
# checked by src/docforge/tests/units/test_version_alignment.py. A constant, not package
# metadata: this app runs as scripts (`package = false`), so docforge-mcp is never installed.

__version__ = "0.31.3"
