# ====== Code Summary ======
# SchemaOpsError — an invalid field_ops sequence (unknown name, duplicate add, rename collision…);
# the router maps it to a 422 naming the offending op.


class SchemaOpsError(ValueError):
    """Raised when a ``field_ops`` list cannot be applied to the current schema."""


__all__ = ["SchemaOpsError"]
