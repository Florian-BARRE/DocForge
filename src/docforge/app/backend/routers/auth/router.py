# ====== Code Summary ======
# Auth router: login (public), me, and root's API-key management (create / list / revoke).
# In the keys-only model only the root account logs in, so /auth/keys IS the key-management surface
# and key creation accepts a per-collection capability scope (validated against the taxonomy).
# Login is the only public route here; everything else requires an authenticated principal.
# All persistence goes through CONTEXT repositories; key generation/hashing lives in AuthService.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.auth import CapabilityHelpers, Principal, require_principal
from backend.libs.utils.error_handling import auto_handle_errors
from backend.routers.auth.models import (
    ApiKeyCreatedResponse,
    ApiKeyCreateRequest,
    ApiKeyListResponse,
    ApiKeyRevokeResponse,
    ApiKeySummary,
    LoginRequest,
    LoginResponse,
    MeResponse,
    UserSummary,
)

router = APIRouter(tags=["auth"])


@router.post("/login", response_model=LoginResponse)
@auto_handle_errors
async def login(body: LoginRequest) -> LoginResponse:
    """
    Authenticate a username/password pair and return a JWT access token.

    This is the only public auth route. On success it mints a bearer token the client sends as
    ``Authorization: Bearer <token>`` on subsequent requests.
    """
    # 1. Verify credentials (unknown user / bad password / inactive account all collapse to 401)
    principal = await CONTEXT.auth_service.authenticate(body.username, body.password)
    if principal is None:
        # 401 — invalid credentials. We never reveal which of username/password was wrong.
        CONTEXT.logger.warning(f"Login rejected (401): username={body.username!r}")
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    # 2. Mint an access token and echo back a safe user summary
    token = CONTEXT.auth_service.mint_token(principal)
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user=UserSummary(
            id=principal.user_id,
            username=principal.username,
            role=principal.global_role.value,
            is_active=True,
        ),
    )


@router.get("/me", response_model=MeResponse)
@auto_handle_errors
async def me(principal: Principal = Depends(require_principal)) -> MeResponse:
    """
    Return the authenticated caller's identity.

    Only the root account logs in, so this is always the root identity (full access). Per-collection
    authorization now lives on API keys, not on the logged-in user, so there is nothing else to
    enumerate here.
    """
    # 1. Build the user summary from the resolved principal
    return MeResponse(
        user=UserSummary(
            id=principal.user_id,
            username=principal.username,
            role=principal.global_role.value,
            is_active=True,
        )
    )


@router.post("/keys", response_model=ApiKeyCreatedResponse, status_code=201)
@auto_handle_errors
async def create_api_key(
    body: ApiKeyCreateRequest, principal: Principal = Depends(require_principal)
) -> ApiKeyCreatedResponse:
    """
    Create a new API key (owned by root), optionally scoped to per-collection capabilities.

    The plaintext key is returned EXACTLY ONCE in this response and never again — only its hash is
    stored. The caller must capture it now. When ``permissions`` is provided it is validated against
    the capability taxonomy (422 on a malformed scope) before any key is generated.
    """
    # 1. Validate the REQUIRED permission scope BEFORE generating/persisting anything. A created
    #    key always declares its scope — there is no None/full-access fallback (that sentinel is
    #    reserved for the static root env key). Full access must be requested explicitly via an
    #    all-collections admin entry.
    try:
        CapabilityHelpers.validate_permissions(body.permissions)
    except ValueError as exc:
        # 422 — the supplied permissions scope is malformed or references unknown capabilities.
        CONTEXT.logger.warning(
            f"API key create rejected (422 invalid permissions): user_id={principal.user_id} "
            f"name={body.name!r} error={exc}"
        )
        raise HTTPException(status_code=422, detail=f"Invalid permissions scope: {exc}")

    # 2. Generate the key + its storage fields (plaintext leaves only in this response)
    plaintext_key, key_hash, prefix = CONTEXT.auth_service.generate_api_key()

    # 3. Persist the hash + prefix + scope bound to the current user
    async with CONTEXT.postgres.session() as session:
        api_key = await CONTEXT.api_key_repo.create(
            session,
            user_id=principal.user_id,
            name=body.name,
            key_hash=key_hash,
            prefix=prefix,
            permissions=body.permissions,
        )
        created = ApiKeyCreatedResponse(
            id=api_key.id,
            name=api_key.name,
            prefix=api_key.prefix,
            key=plaintext_key,
            permissions=api_key.permissions,
            created_at=api_key.created_at,
        )

    CONTEXT.logger.info(
        f"Created api_key id={created.id} user_id={principal.user_id} name={body.name!r} "
        f"scoped={body.permissions is not None}"
    )
    return created


@router.get("/keys", response_model=ApiKeyListResponse)
@auto_handle_errors
async def list_api_keys(
    principal: Principal = Depends(require_principal),
) -> ApiKeyListResponse:
    """List the current user's API keys (prefixes + scope only — never the hash or plaintext)."""
    # 1. Read the user's keys (includes revoked ones for the audit trail)
    async with CONTEXT.postgres.session() as session:
        keys = await CONTEXT.api_key_repo.list_for_user(session, principal.user_id)

    # 2. Project to safe summaries (carrying the per-collection scope so the UI can show it)
    summaries = [ApiKeySummary.model_validate(k) for k in keys]
    return ApiKeyListResponse(keys=summaries, total=len(summaries))


@router.delete("/keys/{key_id}", response_model=ApiKeyRevokeResponse)
@auto_handle_errors
async def revoke_api_key(
    key_id: uuid.UUID, principal: Principal = Depends(require_principal)
) -> ApiKeyRevokeResponse:
    """
    Revoke one of the current user's own API keys (soft revoke).

    Scoped to the caller: a user can only revoke their own keys.
    """
    # 1. Soft-revoke the key, scoped to the owner (a non-owned / unknown / already-revoked key
    #    simply yields revoked=False — no information about other users' keys is leaked).
    async with CONTEXT.postgres.session() as session:
        revoked = await CONTEXT.api_key_repo.revoke(session, key_id, principal.user_id)
    if not revoked:
        # 404 — no active key with this id owned by the caller (unknown, foreign, or already revoked).
        CONTEXT.logger.warning(
            f"API key revoke rejected (404): key={key_id} user_id={principal.user_id}"
        )
        raise HTTPException(status_code=404, detail=f"Active API key {key_id} not found.")

    CONTEXT.logger.info(f"Revoked api_key id={key_id} user_id={principal.user_id}")
    return ApiKeyRevokeResponse(revoked=True, id=key_id)
