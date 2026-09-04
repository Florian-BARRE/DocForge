"""ProviderEgressPolicy — the pure allowlist SSRF guard for provider base URLs. An empty allowlist is
allow-all (the shipped default, guard OFF); a non-empty one admits a destination only when its host
matches an entry (hostname glob OR IP inside a listed CIDR/IP), and refuses anything else — including a
URL whose host cannot be parsed. Pure string/ip work, no engine, no config."""

import pytest

from shared_libs.pipelines.reachability import ProviderEgressPolicy


def test_empty_allowlist_allows_everything() -> None:
    policy = ProviderEgressPolicy.from_spec("")
    assert policy.enabled is False
    assert policy.is_allowed("http://anything.example.com:1234/models") is True
    assert policy.is_allowed("http://10.0.0.5:6333") is True
    assert policy.is_allowed(None) is True  # OFF ignores even an unparseable url


def test_none_spec_is_allow_all() -> None:
    assert ProviderEgressPolicy.from_spec(None).is_allowed("http://x/y") is True


def test_listed_hostname_is_allowed_others_refused() -> None:
    policy = ProviderEgressPolicy.from_spec("bge_server, gotenberg")
    assert policy.enabled is True
    assert policy.is_allowed("http://bge_server:8000/models") is True
    assert policy.is_allowed("http://gotenberg:3000") is True
    # An unlisted host — public OR private — is refused once the guard is on.
    assert policy.is_allowed("https://api.openai.com/v1") is False
    assert policy.is_allowed("http://docforge_qdrant:6333") is False


def test_hostname_glob_matches_case_insensitively() -> None:
    policy = ProviderEgressPolicy.from_spec("*.internal")
    assert policy.is_allowed("http://BGE.INTERNAL:8000") is True
    assert policy.is_allowed("http://bge.internal/models") is True
    assert policy.is_allowed("http://bge.external/models") is False


def test_cidr_entry_matches_ip_hosts_inside_it() -> None:
    policy = ProviderEgressPolicy.from_spec("10.0.0.0/8")
    assert policy.is_allowed("http://10.3.4.5:6333") is True
    assert policy.is_allowed("http://11.0.0.1:6333") is False
    # A CIDR entry does NOT match a hostname (only IP-literal hosts).
    assert policy.is_allowed("http://bge_server:8000") is False


def test_single_ip_entry() -> None:
    policy = ProviderEgressPolicy.from_spec("127.0.0.1")
    assert policy.is_allowed("http://127.0.0.1:9000") is True
    assert policy.is_allowed("http://127.0.0.2:9000") is False


def test_mixed_allowlist_hostname_and_cidr() -> None:
    policy = ProviderEgressPolicy.from_spec("bge_server, 192.168.0.0/16")
    assert policy.is_allowed("http://bge_server:8000") is True
    assert policy.is_allowed("http://192.168.5.5:80") is True
    assert policy.is_allowed("http://172.16.0.1:80") is False


@pytest.mark.parametrize("bad", ["", "not-a-url", "://noscheme", "http:///nohost", None])
def test_unparseable_url_is_refused_when_guard_on(bad) -> None:
    policy = ProviderEgressPolicy.from_spec("bge_server")
    assert policy.is_allowed(bad) is False


def test_blank_entries_are_dropped() -> None:
    # Trailing commas / whitespace-only entries must not create an empty '' glob that matches nothing
    # weirdly — they are simply dropped, leaving a clean allowlist.
    policy = ProviderEgressPolicy.from_spec(" bge_server , , ")
    assert policy.allow == ("bge_server",)
    assert policy.is_allowed("http://bge_server:8000") is True
