# ====== Code Summary ======
# The typed input-validation error for the cost estimate. Raised by CostEstimateService when the
# CALLER's request is bad (a non-UUID document id, an unknown/foreign id, or an invalid corpus
# filter) — the cases the router maps to a 422. It subclasses ValueError so any existing
# ValueError-aware caller still catches it, but naming it lets the router narrow its ``except`` to
# CALLER faults only, so an UNRELATED ValueError raised deep in the estimator's arithmetic surfaces
# as a 500 (a real bug) instead of being silently masked as a client 422.


class EstimateInputError(ValueError):
    """A bad estimate REQUEST (non-UUID / unknown-or-foreign id / invalid corpus filter) → 422."""


__all__ = ["EstimateInputError"]
