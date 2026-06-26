# ====== Code Summary ======
# Unit tests for the capability taxonomy (backend.libs.auth.capabilities): role → capability
# expansion, the per-collection grants() predicate (exact id + wildcard), custom entries, and
# permissions-scope validation. Pure functions — no DB, no FastAPI.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from backend.libs.auth.capabilities import Capability, CapabilityHelpers


class TestRoleExpansion:
    """read ⊂ write ⊂ admin; custom uses the explicit list."""

    def test_read_expands_to_read_set(self) -> None:
        caps = CapabilityHelpers.expand_entry({"collection_id": "*", "role": "read"})
        assert caps == {Capability.DOCUMENTS_READ, Capability.SEARCH, Capability.CONFIG_READ}

    def test_write_includes_read(self) -> None:
        caps = CapabilityHelpers.expand_entry({"collection_id": "*", "role": "write"})
        assert {Capability.DOCUMENTS_READ, Capability.SEARCH, Capability.CONFIG_READ} <= caps
        assert Capability.DOCUMENTS_WRITE in caps
        assert Capability.CHUNKS_WRITE in caps
        assert Capability.CONFIG_WRITE in caps
        assert Capability.COLLECTION_ADMIN not in caps

    def test_admin_includes_collection_admin(self) -> None:
        caps = CapabilityHelpers.expand_entry({"collection_id": "*", "role": "admin"})
        assert Capability.COLLECTION_ADMIN in caps
        assert Capability.DOCUMENTS_WRITE in caps

    def test_custom_uses_explicit_capabilities(self) -> None:
        entry = {"collection_id": "*", "role": "custom", "capabilities": ["search"]}
        assert CapabilityHelpers.expand_entry(entry) == {Capability.SEARCH}

    def test_unknown_role_grants_nothing(self) -> None:
        assert CapabilityHelpers.expand_entry({"collection_id": "*", "role": "boss"}) == set()


class TestGrants:
    """grants() matches the path collection (exact id or '*') and checks the capability."""

    def test_exact_collection_match(self) -> None:
        cid = str(uuid.uuid4())
        perms = {"entries": [{"collection_id": cid, "role": "read"}]}
        assert CapabilityHelpers.grants(perms, cid, Capability.DOCUMENTS_READ) is True
        assert CapabilityHelpers.grants(perms, cid, Capability.DOCUMENTS_WRITE) is False

    def test_other_collection_denied(self) -> None:
        cid_a, cid_b = str(uuid.uuid4()), str(uuid.uuid4())
        perms = {"entries": [{"collection_id": cid_a, "role": "admin"}]}
        assert CapabilityHelpers.grants(perms, cid_b, Capability.DOCUMENTS_READ) is False

    def test_wildcard_matches_any_collection(self) -> None:
        perms = {"entries": [{"collection_id": "*", "role": "write"}]}
        assert CapabilityHelpers.grants(perms, str(uuid.uuid4()), Capability.DOCUMENTS_WRITE) is True

    def test_empty_entries_denies(self) -> None:
        assert CapabilityHelpers.grants({"entries": []}, str(uuid.uuid4()), Capability.SEARCH) is False


class TestValidatePermissions:
    """validate_permissions raises ValueError on any malformed scope."""

    def test_valid_scope_passes(self) -> None:
        CapabilityHelpers.validate_permissions(
            {"entries": [{"collection_id": "*", "role": "read"}]}
        )

    def test_valid_custom_scope_passes(self) -> None:
        CapabilityHelpers.validate_permissions(
            {"entries": [{"collection_id": str(uuid.uuid4()), "role": "custom",
                          "capabilities": ["documents.read", "search"]}]}
        )

    def test_empty_entries_rejected(self) -> None:
        with pytest.raises(ValueError):
            CapabilityHelpers.validate_permissions({"entries": []})

    def test_unknown_role_rejected(self) -> None:
        with pytest.raises(ValueError):
            CapabilityHelpers.validate_permissions(
                {"entries": [{"collection_id": "*", "role": "superadmin"}]}
            )

    def test_custom_without_capabilities_rejected(self) -> None:
        with pytest.raises(ValueError):
            CapabilityHelpers.validate_permissions(
                {"entries": [{"collection_id": "*", "role": "custom"}]}
            )

    def test_custom_with_unknown_capability_rejected(self) -> None:
        with pytest.raises(ValueError):
            CapabilityHelpers.validate_permissions(
                {"entries": [{"collection_id": "*", "role": "custom",
                              "capabilities": ["documents.read", "bogus.cap"]}]}
            )

    def test_missing_collection_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            CapabilityHelpers.validate_permissions({"entries": [{"role": "read"}]})
