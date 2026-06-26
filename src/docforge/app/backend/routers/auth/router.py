# ====== Code Summary ======
# Auth router: login (public), me, and per-user API-key management (create / list / revoke).
# Login is the only public route here; everything else requires an authenticated principal.
# All persistence goes through CONTEXT repositories; key generation/hashing lives in AuthService.

# ====== Standard Library Imports ======
import uuid

# ====== Third-Party Library Imports ======
from fastapi import APIRouter, Depends, HTTPException

# ====== Internal Project Imports ======
from backend.context import CONTEXT
from backend.libs.auth import Principal, require_principal
from backend.libs.utils.error_handling import auto_handle_errors
from backend.routers.auth.models import (
    ApiKeyCreatedResponse,
    ApiKeyCreateRequest,
    ApiKeyListResponse,
    ApiKeyRevokeResponse,
    ApiKeySummary,
    CollectionGrantSummary,
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
    Return the authenticated caller's identity and their per-collection grants.

    Root receives an empty grant list (root holds implicit admin on every collection), which the
    frontend interprets via the user's role rather than the grant list.
    """
    # 1. Build the user summary from the resolved principal
    user = UserSummary(
        id=principal.user_id,
        username=principal.username,
        role=principal.global_role.value,
        is_active=True,
    )

    # 2. Root has implicit admin everywhere — no explicit grants to enumerate. impersonated_by is
    #    still echoed so a root impersonating ANOTHER root would still surface the "acting as" tag.
    if principal.is_root:
        return MeResponse(user=user, grants=[], impersonated_by=principal.impersonated_by)

    # 3. List the user's explicit grants
    async with CONTEXT.postgres.session() as session:
        ids = await CONTEXT.grant_repo.list_collection_ids_for_user(session, principal.user_id)
        grants = [
            await CONTEXT.grant_repo.get(session, principal.user_id, cid) for cid in ids
        ]
    summaries = [
        CollectionGrantSummary(collection_id=g.collection_id, role=g.role)
        for g in grants
        if g is not None
    ]
    # impersonated_by is set when this session was minted by a root impersonating the user.
    return MeResponse(user=user, grants=summaries, impersonated_by=principal.impersonated_by)


@router.post("/keys", response_model=ApiKeyCreatedResponse, status_code=201)
@auto_handle_errors
async def create_api_key(
    body: ApiKeyCreateRequest, principal: Principal = Depends(require_principal)
) -> ApiKeyCreatedResponse:
    """
    Create a new API key for the current user.

    The plaintext key is returned EXACTLY ONCE in this response and never again — only its hash is
    stored. The caller must capture it now.
    """
    # 1. Generate the key + its storage fields (plaintext leaves only in this response)
    plaintext_key, key_hash, prefix = CONTEXT.auth_service.generate_api_key()

    # 2. Persist the hash + prefix bound to the current user
    async with CONTEXT.postgres.session() as session:
        api_key = await CONTEXT.api_key_repo.create(
            session,
            user_id=principal.user_id,
            name=body.name,
            key_hash=key_hash,
            prefix=prefix,
        )
        created = ApiKeyCreatedResponse(
            id=api_key.id,
            name=api_key.name,
            prefix=api_key.prefix,
            key=plaintext_key,
            created_at=api_key.created_at,
        )

    CONTEXT.logger.info(
        f"Created api_key id={created.id} user_id={principal.user_id} name={body.name!r}"
    )
    return created


@router.get("/keys", response_model=ApiKeyListResponse)
@auto_handle_errors
async def list_api_keys(
    principal: Principal = Depends(require_principal),
) -> ApiKeyListResponse:
    """List the current user's API keys (prefixes only — never the hash or plaintext)."""
    # 1. Read the user's keys (includes revoked ones for the audit trail)
    async with CONTEXT.postgres.session() as session:
        keys = await CONTEXT.api_key_repo.list_for_user(session, principal.user_id)

    # 2. Project to safe summaries
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
