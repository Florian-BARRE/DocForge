# Only the per-stage Config class survives here (imported by full path by the builder adapter);
# the v1 stage/step nodes are deleted — the flow stage package replaces them.
from .config import *  # noqa: F401,F403 — re-export the stage Config
