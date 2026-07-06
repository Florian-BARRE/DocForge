# ---------------------- Node families auto-discovery ---------------------- #
# Importing this package imports every node family below it (which in turn imports their nodes),
# so the whole catalogue registers itself just by being present on disk.
from shared_libs.pipelines.registry import NodeRegistry

NodeRegistry.auto_import(__name__)
