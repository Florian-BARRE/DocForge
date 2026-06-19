# ====== Code Summary ======
# Internal helpers shared across pipeline_config sub-modules:
# credential detection (_is_secret_key / _SECRET_SEGMENTS), recursive secret
# redaction (_redact), and the backward-compat provider-spec lifting utility
# (_lift_provider_to_chain).
#
# PipelineConfigHelpers wraps the logic as a static-only class. Module-level
# function names are preserved as thin wrappers for backward compat.
#
# LEAF CONSTRAINT: no module-level import of libs.providers / libs.data /
# libs.pipeline / libs.config.

# ====== Standard Library Imports ======
from __future__ import annotations

import re
from typing import Any

# ====== Internal Project Imports ======
from libs.config.pipeline.spec_utils import flatten_provider_spec as _flatten_provider_spec

# Param-name segments that mark a value as a credential — masked when the config is echoed.
# Matched against whole `_`/`-`-separated segments (not substrings) so legitimate keys like
# "max_tokens" are never mistaken for a "token" credential.
_SECRET_SEGMENTS = frozenset({"key", "apikey", "token", "secret", "password", "credential", "auth"})


class PipelineConfigHelpers:
    """
    Static-only helper class for pipeline_config internal utilities.

    Provides credential detection, recursive secret redaction, and the
    backward-compat provider-spec lifting utility used by stage config validators.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only helper class."""
        raise TypeError(f"{cls.__name__} is a static-only class and cannot be instantiated.")

    @staticmethod
    def is_secret_key(key: str) -> bool:
        """
        Return True when a param name denotes a credential (segment-exact match).

        Args:
            key (str): Parameter name to check.

        Returns:
            bool: True if any word segment in the key matches a known secret segment.
        """
        return any(part in _SECRET_SEGMENTS for part in re.split(r"[_\-\s]+", key.lower()))

    @staticmethod
    def redact(value: Any) -> Any:
        """
        Recursively mask secret-looking keys in a JSON-compatible structure.

        Args:
            value (Any): A JSON-compatible value (dict, list, or scalar).

        Returns:
            Any: The same structure with credential-named keys replaced by "•••".
        """
        # 1. Dict → mask matching keys, recurse into the rest
        if isinstance(value, dict):
            out: dict[str, Any] = {}
            for k, v in value.items():
                if isinstance(k, str) and PipelineConfigHelpers.is_secret_key(k) and v:
                    out[k] = "•••"
                else:
                    out[k] = PipelineConfigHelpers.redact(v)
            return out
        # 2. List → recurse element-wise
        if isinstance(value, list):
            return [PipelineConfigHelpers.redact(v) for v in value]
        # 3. Scalar → unchanged
        return value

    @staticmethod
    def lift_provider_to_chain(v: dict[str, Any], chain_key: str, provider_key: str) -> dict[str, Any]:
        """
        Backward compat for the chain refactor: lift a legacy ``{provider_key: {...}}``
        entry to ``{chain_key: [{...}]}`` so old DB rows still deserialise after the
        single-provider → chain transition.

        Args:
            v (dict): The sub-config dict being validated.
            chain_key (str): Field name of the new chain list (e.g. ``"chain"``).
            provider_key (str): Field name of the legacy single provider (e.g. ``"provider"``).

        Returns:
            dict: ``v`` with the legacy key removed and the chain populated when applicable.
        """
        if provider_key in v and chain_key not in v:
            prov = v.pop(provider_key)
            if prov:
                v[chain_key] = [_flatten_provider_spec(prov)]
            else:
                v[chain_key] = []
        elif chain_key in v and isinstance(v[chain_key], list):
            v[chain_key] = [
                _flatten_provider_spec(item) if isinstance(item, dict) else item
                for item in v[chain_key]
            ]
        return v


# ── Module-level function wrappers — keep private function names importable ──
# These are imported by chunk_embed.py, parse_enrich.py, and the pipeline_config __init__.py.

def _is_secret_key(key: str) -> bool:
    """
    Return True when a param name denotes a credential (segment-exact match).

    Thin wrapper around ``PipelineConfigHelpers.is_secret_key``.

    Args:
        key (str): Parameter name to check.

    Returns:
        bool: True if any word segment in the key matches a known secret segment.
    """
    return PipelineConfigHelpers.is_secret_key(key)


def _redact(value: Any) -> Any:
    """
    Recursively mask secret-looking keys in a JSON-compatible structure.

    Thin wrapper around ``PipelineConfigHelpers.redact``.

    Args:
        value (Any): A JSON-compatible value (dict, list, or scalar).

    Returns:
        Any: The same structure with credential-named keys replaced by "•••".
    """
    return PipelineConfigHelpers.redact(value)


def _lift_provider_to_chain(v: dict[str, Any], chain_key: str, provider_key: str) -> dict[str, Any]:
    """
    Backward compat for the chain refactor.

    Thin wrapper around ``PipelineConfigHelpers.lift_provider_to_chain``.

    Args:
        v (dict): The sub-config dict being validated.
        chain_key (str): Field name of the new chain list.
        provider_key (str): Field name of the legacy single provider.

    Returns:
        dict: ``v`` with the legacy key removed and the chain populated when applicable.
    """
    return PipelineConfigHelpers.lift_provider_to_chain(v, chain_key, provider_key)
