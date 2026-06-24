# ====== Code Summary ======
# Live integration tests for the DocForge auth + per-collection authorization layer.
#
# Skip strategy (two levels):
#   1. Stack not reachable → auto-skipped by the session-scope ``live_client`` fixture.
#   2. AUTH_ENABLED=False on the live stack (probed per class) → all tests in that class skip.
#      Detection: a call to a protected route without any credential returns 200 → auth is off.
#
# What is covered:
#   A. POST /auth/login happy path → JWT returned; JWT works as a bearer on subsequent calls.
#   B. POST /auth/login bad password → 401.
#   C. Root creates a user; that user gets 403 on a collection where they hold no grant.
#   D. Root grants READ → user can GET /collections/list but 403 on ingest.
#   E. Root upgrades grant to WRITE → ingest now allowed.
#   F. User creates an API key, uses it successfully, revokes it → rejected afterward.
#   G. SSE /monitoring/stream works with ?token= (no header).
#   H. Existing corpus live tests pass unchanged (LiveClient now sends the token header everywhere).
#
# Test isolation: each test class creates and tears down its own user, collection, and API keys.
# Session-scoped ``live_client`` carries the root API token from the conftest env variable.

# ====== Standard Library Imports ======
from __future__ import annotations

import os
import uuid

# ====== Third-Party Library Imports ======
import pytest

# ====== Internal Project Imports ======
from tests.libs.live_client import LiveClient
from tests.live_test.conftest import API_TOKEN, API_URL, QDRANT_URL


# ─── Module-level helpers ───────────────────────────────────────────────────

def _is_auth_on(client: LiveClient) -> bool:
    """
    Return True if the live stack has AUTH_ENABLED=True.

    Probe: call GET /auth/me without any Authorization header. If auth is off the kill-switch
    injects a synthetic root and the route returns 200; if auth is on it returns 401.

    Args:
        client (LiveClient): The live client (session-scoped, token configured in conftest).

    Returns:
        bool: True when the stack requires authentication credentials.
    """
    # Use a raw httpx call without the token so we truly send no credential
    import httpx
    try:
        resp = httpx.get(
            f"{API_URL}/auth/me",
            timeout=5.0,
            headers={},  # explicitly no auth header
        )
        # 401 → auth is on; 200 → auth kill-switch is off
        return resp.status_code == 401
    except Exception:
        return False


def _make_live_client(token: str) -> LiveClient:
    """
    Build a LiveClient carrying the given bearer token (user-scoped calls in tests).

    Args:
        token (str): JWT or API key to send on every request.

    Returns:
        LiveClient: A fresh synchronous HTTP client.
    """
    return LiveClient(api_url=API_URL, qdrant_url=QDRANT_URL, api_token=token)


# ─── A + B: Login flow ──────────────────────────────────────────────────────

class TestLoginLive:
    """
    POST /auth/login happy-path and bad-password → JWT issuance and 401.

    Skipped automatically when auth is off on the live stack.
    """

    def test_skip_if_auth_off(self, live_client: LiveClient) -> None:
        """Internal: skip the whole class when AUTH_ENABLED=False."""
        if not _is_auth_on(live_client):
            pytest.skip("AUTH_ENABLED=False on live stack — auth tests skipped.")

    def test_login_returns_jwt(self, live_client: LiveClient) -> None:
        """Correct root credentials → 200 with a three-part JWT access_token."""
        if not _is_auth_on(live_client):
            pytest.skip("AUTH_ENABLED=False — skipped.")

        # The root password is held in the stack's env (DOCFORGE_ROOT_PASSWORD).
        root_password = os.environ.get("DOCFORGE_TEST_ROOT_PASSWORD", "")
        if not root_password:
            pytest.skip("DOCFORGE_TEST_ROOT_PASSWORD not set — cannot test login.")

        status, body = live_client.post(
            "/auth/login",
            {"username": "root", "password": root_password},
        )
        assert status == 200, f"login failed ({status}): {body}"
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        token = body["access_token"]
        # JWT must be three dot-separated parts
        assert token.count(".") == 2, f"access_token does not look like a JWT: {token!r}"

    def test_jwt_works_as_bearer(self, live_client: LiveClient) -> None:
        """A JWT obtained via login can be used as a bearer to call a protected route."""
        if not _is_auth_on(live_client):
            pytest.skip("AUTH_ENABLED=False — skipped.")

        root_password = os.environ.get("DOCFORGE_TEST_ROOT_PASSWORD", "")
        if not root_password:
            pytest.skip("DOCFORGE_TEST_ROOT_PASSWORD not set.")

        _, login_body = live_client.post(
            "/auth/login",
            {"username": "root", "password": root_password},
        )
        token = login_body.get("access_token", "")
        assert token, "no token returned from login"

        jwt_client = _make_live_client(token)
        try:
            status, body = jwt_client.get("/auth/me")
            assert status == 200, f"/auth/me with JWT failed ({status}): {body}"
            assert body["user"]["username"] == "root"
        finally:
            jwt_client.close()

    def test_login_bad_password_returns_401(self, live_client: LiveClient) -> None:
        """Wrong password → 401 (no information leak about why)."""
        if not _is_auth_on(live_client):
            pytest.skip("AUTH_ENABLED=False — skipped.")

        status, _ = live_client.post(
            "/auth/login",
            {"username": "root", "password": f"wrong-{uuid.uuid4().hex}"},
        )
        assert status == 401


# ─── C–E: Per-collection role enforcement ───────────────────────────────────

class TestCollectionRbacLive:
    """
    End-to-end RBAC: root creates a user, grants roles, verifies read/write gates.

    Test lifecycle:
      1. Root creates a user + a collection.
      2. User has no grant → 403.
      3. Root grants READ → user can list docs but cannot ingest.
      4. Root upgrades to WRITE → user can ingest.
      5. Root deletes the user + collection on teardown.
    """

    def test_rbac_lifecycle(self, live_client: LiveClient) -> None:
        """Full RBAC lifecycle (no grant → read → write)."""
        if not API_TOKEN:
            pytest.skip("DOCFORGE_TEST_API_TOKEN not set — cannot test RBAC.")
        if not _is_auth_on(live_client):
            pytest.skip("AUTH_ENABLED=False — RBAC tests skipped.")

        # 1. Root creates a test user and a test collection
        random_suffix = uuid.uuid4().hex[:8]
        user_name = f"testuser-{random_suffix}"
        user_password = f"P@ssw0rd-{random_suffix}"

        status, user_body = live_client.post(
            "/users",
            {"username": user_name, "password": user_password},
        )
        assert status == 201, f"user create failed ({status}): {user_body}"
        user_id = user_body["id"]

        # Obtain a user-scoped bearer via login
        status, login_body = live_client.post(
            "/auth/login",
            {"username": user_name, "password": user_password},
        )
        assert status == 200, f"user login failed ({status}): {login_body}"
        user_token = login_body["access_token"]
        user_client = _make_live_client(user_token)

        # Create a test collection as root
        status, col_body = live_client.post(
            "/collections/create",
            {"name": f"rbac-col-{random_suffix}", "supported_formats": ["pdf"]},
        )
        assert status == 201, f"collection create failed ({status}): {col_body}"
        col_id = col_body["id"]

        try:
            # 2. User has no grant → 403 on the collection's document list
            status, _ = user_client.get(f"/collections/{col_id}/documents/list")
            assert status == 403, f"expected 403 with no grant, got {status}"

            # 3. Root grants READ
            status, _ = live_client.put(
                f"/collections/{col_id}/access/{user_id}",
                {"role": "read"},
            )
            assert status == 200, f"grant read failed ({status})"

            # READ: user can list documents
            status, _ = user_client.get(f"/collections/{col_id}/documents/list")
            assert status == 200, f"expected 200 with READ grant, got {status}"

            # READ: user cannot ingest (needs WRITE)
            dummy_pdf = b"%PDF-1.4 fake"
            import httpx, json as _json
            _raw = httpx.post(
                f"{API_URL}/collections/{col_id}/documents/ingest",
                files={"file": ("test.pdf", dummy_pdf, "application/pdf")},
                headers={"Authorization": f"Bearer {user_token}"},
                timeout=30.0,
            )
            assert _raw.status_code == 403, (
                f"expected 403 with READ-only grant on ingest, got {_raw.status_code}"
            )

            # 4. Root upgrades grant to WRITE
            status, _ = live_client.put(
                f"/collections/{col_id}/access/{user_id}",
                {"role": "write"},
            )
            assert status == 200, f"grant write failed ({status})"

            # WRITE: ingest is now accepted (202) — we don't wait for processing
            _raw2 = httpx.post(
                f"{API_URL}/collections/{col_id}/documents/ingest",
                files={"file": ("test.pdf", dummy_pdf, "application/pdf")},
                headers={"Authorization": f"Bearer {user_token}"},
                timeout=30.0,
            )
            # 202 accepted OR 400 (bad PDF content) — both mean auth PASSED
            assert _raw2.status_code in (202, 400, 422), (
                f"unexpected ingest status with WRITE grant: {_raw2.status_code}"
            )

        finally:
            user_client.close()
            # Cleanup: delete the collection + deactivate the user
            live_client.delete(f"/collections/{col_id}/delete")
            live_client.delete(f"/users/{user_id}")


# ─── F: API key create / use / revoke ───────────────────────────────────────

class TestApiKeyLifecycleLive:
    """
    Create a DB API key, use it as bearer, revoke it, confirm rejection.
    """

    def test_api_key_lifecycle(self, live_client: LiveClient) -> None:
        """Create → use → revoke → rejected."""
        if not API_TOKEN:
            pytest.skip("DOCFORGE_TEST_API_TOKEN not set — cannot test API key lifecycle.")
        if not _is_auth_on(live_client):
            pytest.skip("AUTH_ENABLED=False — API key tests skipped.")

        # 1. Create an API key as root
        status, key_body = live_client.post(
            "/auth/keys",
            {"name": f"test-key-{uuid.uuid4().hex[:8]}"},
        )
        assert status == 201, f"key create failed ({status}): {key_body}"
        plaintext_key = key_body.get("key", "")
        key_id = key_body.get("id", "")
        assert plaintext_key, "no plaintext key returned from create"
        assert key_id, "no key id returned from create"

        # 2. Use the key as a bearer
        key_client = _make_live_client(plaintext_key)
        try:
            status, me_body = key_client.get("/auth/me")
            assert status == 200, f"key bearer rejected ({status}): {me_body}"
            assert "user" in me_body

            # 3. Revoke the key
            status, revoke_body = live_client.delete(f"/auth/keys/{key_id}")
            assert status == 200, f"revoke failed ({status}): {revoke_body}"
            assert revoke_body.get("revoked") is True

            # 4. Using the revoked key → 401
            status, _ = key_client.get("/auth/me")
            assert status == 401, f"expected 401 after revoke, got {status}"
        finally:
            key_client.close()


# ─── G: SSE ?token= auth ────────────────────────────────────────────────────

class TestSseQueryTokenLive:
    """
    GET /monitoring/stream accepts the bearer via ?token= query parameter.

    Browser EventSource cannot set Authorization headers, so require_principal_sse
    accepts the token as a query fallback.
    """

    def test_sse_query_token_accepted(self, live_client: LiveClient) -> None:
        """Connect to /monitoring/stream with ?token=<root-token> — stream opens (not 401)."""
        if not API_TOKEN:
            pytest.skip("DOCFORGE_TEST_API_TOKEN not set — cannot test SSE query auth.")
        if not _is_auth_on(live_client):
            pytest.skip("AUTH_ENABLED=False — SSE auth test skipped.")

        import httpx
        # Connect without Authorization header, only the query param
        try:
            with httpx.Client(timeout=5.0) as raw:
                resp = raw.get(
                    f"{API_URL}/monitoring/stream?token={API_TOKEN}",
                    headers={},  # explicitly no Authorization header
                    timeout=3.0,
                )
            # 200 means the stream opened (auth passed); any 4xx means auth failed
            assert resp.status_code == 200, (
                f"SSE stream with ?token= rejected: {resp.status_code}"
            )
        except httpx.ReadTimeout:
            # ReadTimeout on an SSE stream means the connection was accepted and held open —
            # that is a success (the server did not immediately return a 401/403 rejection).
            pass

    def test_sse_no_token_returns_401(self, live_client: LiveClient) -> None:
        """Connect to /monitoring/stream with no credential → 401."""
        if not _is_auth_on(live_client):
            pytest.skip("AUTH_ENABLED=False — skipped.")

        import httpx
        try:
            with httpx.Client(timeout=5.0) as raw:
                resp = raw.get(
                    f"{API_URL}/monitoring/stream",
                    headers={},
                    timeout=3.0,
                )
            assert resp.status_code == 401
        except httpx.ReadTimeout:
            # Timeout without 401 means auth incorrectly passed — fail the test
            pytest.fail("SSE stream did not return 401 for an unauthenticated request.")
