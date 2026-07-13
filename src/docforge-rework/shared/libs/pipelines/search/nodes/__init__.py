# ---------------------- Search-pipeline nodes, grouped by STAGE ---------------------- #
# One subpackage per search stage (query · encode · retrieve · fuse · rerank · postprocess) plus the
# reused deliver family (the hits kind): importing each registers its family metadata and every node
# inside it. Importing this package is all a consumer needs to make the search palette + graph
# buildable. The shared base.py / placeholder.py modules register nothing.
import shared_libs.pipelines.search.nodes.deliver  # noqa: F401
import shared_libs.pipelines.search.nodes.encode  # noqa: F401
import shared_libs.pipelines.search.nodes.fuse  # noqa: F401
import shared_libs.pipelines.search.nodes.postprocess  # noqa: F401
import shared_libs.pipelines.search.nodes.query  # noqa: F401
import shared_libs.pipelines.search.nodes.rerank  # noqa: F401
import shared_libs.pipelines.search.nodes.retrieve  # noqa: F401
