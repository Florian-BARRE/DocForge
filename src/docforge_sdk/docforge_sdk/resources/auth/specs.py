# ====== Code Summary ======
# The auth (API-key management) resource. All URL/body logic lives once in the pure _AuthSpecs mixin,
# so AsyncAuth and SyncAuth have identical public surfaces whose bodies differ ONLY by ``await``. The
# rotate path preserves the backend's "absent != null" contract by dumping with exclude_unset (see
# _AuthSpecs._rotate_spec) and only threading through the fields the caller actually set.

# ====== Standard Library Imports ======
from datetime import datetime
from types import EllipsisType

# ====== Local Project Imports ======
from ..._requestspec import RequestSpec
from ...models._shared import KeyPermissions
from ...models.auth import CreateKeyRequest, RotateKeyRequest
from .._base import _ResourceMixin


class _AuthSpecs(_ResourceMixin):
    """
    Pure ``RequestSpec`` builders for the auth endpoints — the single source of URL/body logic.

    Shared verbatim by the async and sync resources so neither ever hand-rolls a URL or a body dump.
    """

    _KEYS_PATH = "/auth/keys"

    def _create_spec(self, request: CreateKeyRequest) -> RequestSpec:
        """
        Build the spec for creating a key.

        Args:
            request (CreateKeyRequest): The create-key body.

        Returns:
            RequestSpec: A POST to the keys collection carrying the full body.
        """
        return RequestSpec("POST", self._KEYS_PATH, json=request.model_dump(mode="json"))

    def _list_spec(self) -> RequestSpec:
        """
        Build the spec for listing keys.

        Returns:
            RequestSpec: A GET on the keys collection.
        """
        return RequestSpec("GET", self._KEYS_PATH)

    def _revoke_spec(self, key_id: str) -> RequestSpec:
        """
        Build the spec for revoking a key.

        Args:
            key_id (str): The id of the key to revoke.

        Returns:
            RequestSpec: A DELETE on the key resource.
        """
        return RequestSpec("DELETE", f"{self._KEYS_PATH}/{key_id}")

    def _rotate_spec(self, key_id: str, request: RotateKeyRequest) -> RequestSpec:
        """
        Build the spec for rotating a key, preserving the "absent != null" body contract.

        The body is dumped with ``exclude_unset=True`` so a field the caller never set is omitted
        (the backend then clones it from the source key), while an explicitly provided ``None`` is
        serialised as JSON ``null``.

        Args:
            key_id (str): The id of the key to rotate.
            request (RotateKeyRequest): The rotate body carrying only the caller-set fields.

        Returns:
            RequestSpec: A POST to the key's rotate endpoint with a minimal, intent-preserving body.
        """
        return RequestSpec(
            "POST",
            f"{self._KEYS_PATH}/{key_id}/rotate",
            json=request.model_dump(mode="json", exclude_unset=True),
        )

    @staticmethod
    def _build_rotate_request(
        name: str | None | EllipsisType,
        permissions: KeyPermissions | None | EllipsisType,
        expires_at: datetime | None | EllipsisType,
    ) -> RotateKeyRequest:
        """
        Build a RotateKeyRequest from only the caller-supplied fields (``...`` = not supplied).

        Using ``model_validate`` on a dict of provided fields sets ``model_fields_set`` to exactly
        those keys, which is what makes the later ``exclude_unset`` dump omit the untouched ones.

        Args:
            name (str | None | EllipsisType): New label, or ``...`` to leave unset.
            permissions (KeyPermissions | None | EllipsisType): New scope, or ``...`` to leave unset.
            expires_at (datetime | None | EllipsisType): New expiry, or ``...`` to leave unset.

        Returns:
            RotateKeyRequest: A request whose set fields are exactly the supplied ones.
        """
        # 1. Collect only the fields the caller actually passed (Ellipsis means "not supplied").
        provided: dict[str, object] = {}
        if name is not ...:
            provided["name"] = name
        if permissions is not ...:
            provided["permissions"] = permissions
        if expires_at is not ...:
            provided["expires_at"] = expires_at

        # 2. Validate from the dict so model_fields_set carries exactly the supplied keys.
        return RotateKeyRequest.model_validate(provided)

    def _whoami_spec(self) -> RequestSpec:
        """A GET of the calling token's own capabilities + collection scope."""
        return RequestSpec("GET", "/auth/whoami")
