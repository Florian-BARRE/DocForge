# ====== Code Summary ======
# SecretReentryRequired — the refusal raised by the secret write path (BlobSecrets.restore) when a write
# would carry a stored or inherited provider secret onto another endpoint. A ValueError so every write
# route maps it to a 422. Public import path: ``shared_libs.pipelines.blob_secrets``.


class SecretReentryRequired(ValueError):
    """
    Raised when a write would carry a stored or inherited provider secret onto ANOTHER endpoint.

    A masked / omitted secret means "keep the stored key" only for the same provider at the same
    effective endpoint. When the endpoint moved, carrying it would ship the stored key to a host the
    caller just named (exfiltration), and blanking it would silently persist a keyless provider — so
    the write is refused and the caller must re-send the secret (or ``""`` to clear it). The same
    refusal covers a NESTED endpoint override (a metagen target, a structgen step) pointed at a
    foreign endpoint while omitting its key: it could only work by inheriting the parent's key, which
    is never sent there. A ``ValueError`` so every write route maps it to a 422.
    """

    def __init__(self, fields: list[tuple[str, str]]) -> None:
        self.fields = fields
        named = ", ".join(f"node '{node_id}' {field}" for node_id, field in fields)
        super().__init__(
            f"{named} must be re-entered because its endpoint (base_url) differs from the one the "
            f"secret belongs to — a stored or inherited secret is only used for the same provider at "
            f'the same endpoint; send the secret explicitly (or "" to call it without one)'
        )
