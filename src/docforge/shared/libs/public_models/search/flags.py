# ====== Code Summary ======
# The reserved QuerySpec.flags keys a single search REQUEST uses to tune the stored search graph for
# that one run, without touching the collection's blob: skip the rerank stage, or override the
# retrieve node's fusion strategy. They are run-input DATA (RawQuery.flags → QuerySpec.flags), read by
# the pure nodes from their input — never config, never I/O. Absent keys mean "use the blob".

# The flag a request sets to False to skip the rerank stage for this run (candidates pass through
# untouched). Absent (or anything but False) = the blob decides.
RERANK_FLAG = "rerank"

# The flag a request sets to "rrf" / "dbsf" to override the retrieve node's configured fusion for this
# run. Absent = the node's configured fusion.
FUSION_FLAG = "fusion"

# The fusion strategies a FUSION_FLAG may carry — anything else is ignored by the retrieve node.
FUSION_STRATEGIES: frozenset[str] = frozenset({"rrf", "dbsf"})

__all__ = ["RERANK_FLAG", "FUSION_FLAG", "FUSION_STRATEGIES"]
