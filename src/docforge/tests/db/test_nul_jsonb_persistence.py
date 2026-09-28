# ====== Code Summary ======
# Reproduces the PROD crash against a REAL Postgres and proves the fix: a JSONB value carrying a NUL
# (U+0000) — exactly the generated-metadata shape that killed the job — is rejected by Postgres with
# asyncpg's UntranslatableCharacterError, and TextSanitizer.strip_nul makes the same value insertable.
# Guards the DB-edge net the translator applies before every text/jsonb write. The NUL is built with
# chr(0) so this source file itself never contains a raw null byte (Python cannot parse one).

# ====== Standard Library Imports ======
import json
from collections.abc import AsyncIterator

# ====== Third-Party Library Imports ======
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

# ====== Internal Project Imports ======
from shared_libs.public_models import TextSanitizer
from shared_libs.services.db.postgresql import PostgresClient

pytestmark = pytest.mark.db

_NUL = chr(0)
# The exact prod shape: a JSONB value that is a list of generated statements, one with an embedded NUL.
_PROD_VALUE = ["L’AFD est un établissement public.", f"Le service{_NUL} est fait."]


@pytest.fixture
async def client(migrated_db_dsn: str) -> AsyncIterator[PostgresClient]:
    postgres = PostgresClient(migrated_db_dsn)
    try:
        yield postgres
    finally:
        await postgres.dispose()


async def test_raw_nul_jsonb_is_rejected_by_postgres(client: PostgresClient) -> None:
    """The unsanitized value reproduces the prod failure — Postgres cannot store U+0000 in jsonb."""
    with pytest.raises(DBAPIError) as excinfo:
        async with client.session() as session:
            await session.execute(text("SELECT CAST(:v AS jsonb)"), {"v": json.dumps(_PROD_VALUE)})
    message = str(excinfo.value).lower()
    assert "u0000" in message or "untranslatable" in message


async def test_sanitized_nul_jsonb_persists(client: PostgresClient) -> None:
    """After strip_nul the same value casts to jsonb cleanly and round-trips NUL-free."""
    cleaned = TextSanitizer.strip_nul(_PROD_VALUE)
    async with client.session() as session:
        row = await session.execute(
            text("SELECT CAST(:v AS jsonb) AS v"), {"v": json.dumps(cleaned)}
        )
        stored = row.scalar_one()
    assert stored == ["L’AFD est un établissement public.", "Le service est fait."]
    assert all(_NUL not in s for s in stored)
