# ====== Code Summary ======
# Backward-compatible name of the shared sidecar HTML-table flattener, which moved to
# ``sidecar_base.table`` when the four sidecar parsers were factored onto one base.

# ====== Local Project Imports ======
from ..sidecar_base.table import SidecarTableFlattener as PpStructureTableFlattener

__all__ = ["PpStructureTableFlattener"]
