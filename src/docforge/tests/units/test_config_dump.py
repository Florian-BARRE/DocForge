"""ConfigDumpHelpers.masked: the startup config dump must never leak a credential. configplusplus
masks values whose NAME looks like a secret; this helper additionally redacts the ``user:pass@``
userinfo of URL/DSN values (POSTGRES_DSN / REDIS_URL carry the password in the value under a name the
name-heuristic misses). No app bootstrap — the helper is pure string work."""

from shared_libs.observability import ConfigDumpHelpers


class _FakeConfig:
    """Stands in for a rendered RUNTIME_CONFIG (configplusplus already applied its name-based mask)."""

    def __init__(self, text: str) -> None:
        self._text = text

    def __str__(self) -> str:
        return self._text


def test_masks_postgres_dsn_password() -> None:
    out = ConfigDumpHelpers.masked(
        _FakeConfig(
            "POSTGRES_DSN=postgresql+asyncpg://docforge:s3cr3t@docforge_postgres:5432/docforge"
        )
    )
    assert "s3cr3t" not in out
    assert "postgresql+asyncpg://***@docforge_postgres:5432/docforge" in out


def test_masks_redis_url_password_including_userless_form() -> None:
    out = ConfigDumpHelpers.masked(_FakeConfig("REDIS_URL=redis://:redispw@docforge_redis:6379/0"))
    assert "redispw" not in out
    assert "redis://***@docforge_redis:6379/0" in out


def test_preserves_credential_free_urls() -> None:
    """A URL with no userinfo (the common in-stack service alias) is left untouched for diagnostics."""
    out = ConfigDumpHelpers.masked(_FakeConfig("BGE_BASE=http://bge_server:8000/health"))
    assert out == "BGE_BASE=http://bge_server:8000/health"


def test_preserves_name_based_masking_from_the_library() -> None:
    """The helper renders THROUGH the library string, so an already-masked secret stays masked."""
    out = ConfigDumpHelpers.masked(_FakeConfig("AUTH_ROOT_TOKEN=df_…xy (hidden)"))
    assert out == "AUTH_ROOT_TOKEN=df_…xy (hidden)"


def test_redacts_only_userinfo_not_the_path() -> None:
    """Only the authority credentials are dropped — scheme, host, port and path survive."""
    out = ConfigDumpHelpers.masked(_FakeConfig("DSN=scheme://u:p@host:5432/db?opt=1"))
    assert out == "DSN=scheme://***@host:5432/db?opt=1"
