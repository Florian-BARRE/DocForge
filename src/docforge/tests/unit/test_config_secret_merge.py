# ====== Code Summary ======
# Unit tests for ConfigDocument.merge_patch secret preservation.
# Per-collection credentials (api_key, token, …) are entered once in the UI and stored;
# config responses redact them to "•••", so later saves echo that sentinel back. The merge
# must never let a redacted/empty secret overwrite the real stored value — otherwise editing
# any stage would silently wipe the embed/rerank/LLM api_key and break ingestion + search.

from libs.config.validation.document import ConfigDocument

# The redaction sentinel written by PipelineConfig.redacted_dict().
SENTINEL = "•••"


def _base_with_key(key: str = "sk-REAL") -> dict:
    """A stored config document whose embed chain carries a real api_key."""
    return {
        "pipeline": {
            "embed": {"chain": [{"id": "openai", "api_key": key, "model": "text-embedding-3-large"}]},
            "search": {"retrieve": {"rrf_k": 60}},
        }
    }


class TestMergePatchSecretPreservation:
    """A redacted/empty secret in a patch must not overwrite the stored credential."""

    def test_redacted_sentinel_preserved_in_chain(self) -> None:
        base = _base_with_key()
        patch = {"pipeline": {"embed": {"chain": [{"id": "openai", "api_key": SENTINEL, "model": "m"}]}}}
        merged = ConfigDocument.merge_patch(base, patch)
        assert merged["pipeline"]["embed"]["chain"][0]["api_key"] == "sk-REAL"

    def test_empty_secret_preserved(self) -> None:
        base = _base_with_key()
        patch = {"pipeline": {"embed": {"chain": [{"id": "openai", "api_key": "", "model": "m"}]}}}
        merged = ConfigDocument.merge_patch(base, patch)
        assert merged["pipeline"]["embed"]["chain"][0]["api_key"] == "sk-REAL"

    def test_real_new_key_overwrites(self) -> None:
        base = _base_with_key()
        patch = {"pipeline": {"embed": {"chain": [{"id": "openai", "api_key": "sk-NEW", "model": "m"}]}}}
        merged = ConfigDocument.merge_patch(base, patch)
        assert merged["pipeline"]["embed"]["chain"][0]["api_key"] == "sk-NEW"

    def test_search_only_patch_leaves_embed_key_untouched(self) -> None:
        base = _base_with_key()
        patch = {"pipeline": {"search": {"retrieve": {"rrf_k": 30}}}}
        merged = ConfigDocument.merge_patch(base, patch)
        assert merged["pipeline"]["embed"]["chain"][0]["api_key"] == "sk-REAL"
        assert merged["pipeline"]["search"]["retrieve"]["rrf_k"] == 30

    def test_top_level_secret_scalar_preserved(self) -> None:
        base = {"api_key": "sk-REAL", "other": 1}
        merged = ConfigDocument.merge_patch(base, {"api_key": SENTINEL, "other": 2})
        assert merged["api_key"] == "sk-REAL"
        assert merged["other"] == 2

    def test_metadata_fields_replaced_wholesale_when_length_differs(self) -> None:
        # Differing-length dict lists are not provider chains — replace wholesale (allows removals).
        base = {"metadata_fields": [{"field_name": "a"}, {"field_name": "b"}]}
        merged = ConfigDocument.merge_patch(base, {"metadata_fields": [{"field_name": "a"}]})
        assert merged["metadata_fields"] == [{"field_name": "a"}]

    def test_non_secret_field_overwrites_normally(self) -> None:
        base = _base_with_key()
        patch = {"pipeline": {"embed": {"chain": [{"id": "openai", "api_key": SENTINEL, "model": "new-model"}]}}}
        merged = ConfigDocument.merge_patch(base, patch)
        # model (non-secret) updates; api_key (secret, redacted) preserved
        assert merged["pipeline"]["embed"]["chain"][0]["model"] == "new-model"
        assert merged["pipeline"]["embed"]["chain"][0]["api_key"] == "sk-REAL"
