# ------------------- Provider runtimes (L3 bricks) ------------------- #
# Runtime provider implementations consumed ONLY at step level (and by the chain assembler).
# Their @register-decorated CONFIG classes stay in the config layer (common_libs.config /
# common_libs.providers/<family>/<id>/config.py) so the registry + /discovery keep working.
# Per family this package is populated incrementally (P1b inc-4b); embed is the exemplar.

# ------------------- Public API ------------------- #
__all__: list[str] = []
