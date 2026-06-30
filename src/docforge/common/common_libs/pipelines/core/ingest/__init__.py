# The v1 IngestPipeline node + its context/io/errors are deleted (ingestion runs on the flow engine).
# This package now only carries the REUSED pieces under stages/* (pure helpers + per-stage Config
# classes) that the flow stage nodes + the builder import by their full module path.
