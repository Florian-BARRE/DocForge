"""Unit guard for CollectionIndexSignature — the DERIVED reindex fingerprint that replaced the broken
sticky ``needs_reindex`` boolean.

The crux of the fix: the signature must move ONLY for changes that truly invalidate the indexed
vectors — a semantic/lexical/type change on the metadata surface, or an embed-space change — and must
stay STABLE for a ``filterable``-only toggle (its Qdrant payload index is added live by
reconcile_store, needing no reindex). These pins prove exactly that, so the derived flag can never
over-flag a filterable edit nor miss a real vector-space change.
"""

# ====== Standard Library Imports ======
import copy
import hashlib
import json

from shared_libs.pipelines.nodes.embed.dense_sparse import EmbedLegacyMigration

# ====== Internal Project Imports ======
from shared_libs.public_models import FieldType
from shared_libs.services.db.index_signature import CollectionIndexSignature
from shared_libs.services.db.postgresql.tables import MetadataField


def _field(name: str, *, ftype=FieldType.STRING, semantic=False, lexical=False, filterable=False):
    """A transient MetadataField carrying the attributes the signature reads."""
    return MetadataField(
        field_name=name,
        field_type=ftype,
        semantic=semantic,
        lexical=lexical,
        filterable=filterable,
        required=False,
    )


def _embed_blob(*, model: str = "bge-m3", sparse: bool = True) -> dict:
    """A minimal pipeline blob with one embed node whose vector-space config is tunable."""
    return {
        "nodes": [
            {
                "id": "embed_1",
                "kind": "bge_m3",
                "family": "embed",
                "config": {
                    "base_url": "http://bge:80",
                    "model": model,
                    "embed_sparse": sparse,
                    "embed_semantic_fields": [],
                },
            }
        ]
    }


def test_filterable_only_toggle_keeps_signature_stable() -> None:
    """A field flipped filterable (nothing else) must NOT move the signature — reconciled live."""
    blob = _embed_blob()
    before = [_field("author", semantic=True), _field("year", filterable=False)]
    after = [_field("author", semantic=True), _field("year", filterable=True)]
    assert CollectionIndexSignature.compute(blob, before) == CollectionIndexSignature.compute(
        blob, after
    )


def test_semantic_toggle_moves_signature() -> None:
    """Toggling a field semantic changes the named-vector surface → a different signature."""
    blob = _embed_blob()
    before = [_field("author", semantic=False)]
    after = [_field("author", semantic=True)]
    assert CollectionIndexSignature.compute(blob, before) != CollectionIndexSignature.compute(
        blob, after
    )


def test_lexical_toggle_moves_signature() -> None:
    """Toggling a field lexical changes the sparse-vector surface → a different signature."""
    blob = _embed_blob()
    before = [_field("author", lexical=False)]
    after = [_field("author", lexical=True)]
    assert CollectionIndexSignature.compute(blob, before) != CollectionIndexSignature.compute(
        blob, after
    )


def test_type_change_on_vector_field_moves_signature() -> None:
    """Changing the type of a semantic/lexical field moves the signature (its vector space changes)."""
    blob = _embed_blob()
    before = [_field("count", ftype=FieldType.STRING, semantic=True)]
    after = [_field("count", ftype=FieldType.INTEGER, semantic=True)]
    assert CollectionIndexSignature.compute(blob, before) != CollectionIndexSignature.compute(
        blob, after
    )


def test_type_change_on_non_vector_field_keeps_signature_stable() -> None:
    """A type change on a non-searchable (nor filterable) field is irrelevant to the vector space."""
    blob = _embed_blob()
    before = [_field("note", ftype=FieldType.STRING)]
    after = [_field("note", ftype=FieldType.TEXT)]
    assert CollectionIndexSignature.compute(blob, before) == CollectionIndexSignature.compute(
        blob, after
    )


def test_embed_model_change_moves_signature() -> None:
    """A swapped embed model produces incompatible vectors → a different signature (reindex due)."""
    schema = [_field("author", semantic=True)]
    assert CollectionIndexSignature.compute(
        _embed_blob(model="bge-m3"), schema
    ) != CollectionIndexSignature.compute(_embed_blob(model="other"), schema)


def test_embed_sparse_toggle_moves_signature() -> None:
    """Toggling sparse embedding changes the vector space → a different signature."""
    schema = [_field("author", semantic=True)]
    assert CollectionIndexSignature.compute(
        _embed_blob(sparse=True), schema
    ) != CollectionIndexSignature.compute(_embed_blob(sparse=False), schema)


def test_signature_is_order_independent_and_deterministic() -> None:
    """Field order must not move the signature; recomputing the same inputs yields the same hash."""
    blob = _embed_blob()
    schema = [_field("author", semantic=True), _field("title", lexical=True)]
    reordered = list(reversed(copy.deepcopy(schema)))
    sig = CollectionIndexSignature.compute(blob, schema)
    assert sig == CollectionIndexSignature.compute(blob, reordered)
    assert sig == CollectionIndexSignature.compute(blob, schema)
    assert len(sig) == 64  # sha256 hex digest


# ─────────────── pre-slots baselines (dense/sparse slot migration must not flip them) ───────────────

_PRE_SLOTS_KEYS = ("base_url", "model", "embed_sparse", "embed_semantic_fields")


def _pre_slots_signature(blob: dict, schema: list) -> str:
    """A FROZEN copy of the signature the engine stored before the dense/sparse slots existed."""
    embed = sorted(
        (n.get("id"), n.get("kind"), tuple((k, n["config"].get(k)) for k in _PRE_SLOTS_KEYS))
        for n in blob["nodes"]
        if n.get("family") == "embed"
    )
    meta = CollectionIndexSignature._metadata_surface(schema)
    payload = json.dumps({"meta": meta, "embed": embed}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _pre_slots_embed_signature(blob: dict) -> str:
    """The FROZEN pre-slots embed-only baseline (the content-vector signature)."""
    embed = sorted(
        (n.get("id"), n.get("kind"), tuple((k, n["config"].get(k)) for k in _PRE_SLOTS_KEYS))
        for n in blob["nodes"]
        if n.get("family") == "embed"
    )
    return hashlib.sha256(json.dumps(embed, default=str).encode("utf-8")).hexdigest()


def _legacy(kind: str, config: dict) -> dict:
    """A one-node pre-slots embed blob."""
    return {"nodes": [{"id": "embed", "kind": kind, "family": "embed", "config": config}]}


def _migrated(legacy: dict) -> dict:
    """The same blob healed to the (embed, dense_sparse) slot node."""
    node = legacy["nodes"][0]
    kind, config = EmbedLegacyMigration.step(node["kind"], dict(node["config"]))
    return {"nodes": [{**node, "kind": kind, "config": config}]}


def test_legacy_baselines_stay_current_after_the_slot_heal() -> None:
    """A collection indexed pre-slots keeps its baseline once its blob healed to dense_sparse."""
    schema = [_field("author", semantic=True)]
    for kind, config in (
        ("bge_server", {"base_url": "http://bge_server:80"}),
        ("bge_server", {"base_url": "http://bge:80/", "model": "bge-m3", "embed_sparse": True}),
        ("bge_server", {"base_url": "http://bge:80", "embed_sparse": False}),
        ("openai_compatible", {"base_url": "http://emb/v1", "model": "m", "api_key": "k"}),
    ):
        legacy = _legacy(kind, config)
        candidates = CollectionIndexSignature.candidates(_migrated(legacy), schema)
        assert _pre_slots_signature(legacy, schema) in candidates, (kind, config)
        assert _pre_slots_embed_signature(legacy) in CollectionIndexSignature.embed_candidates(
            _migrated(legacy)
        )
        # The canonical fingerprint is the same whichever spelling is stored.
        assert CollectionIndexSignature.compute(legacy, schema) == CollectionIndexSignature.compute(
            _migrated(legacy), schema
        )


def test_a_real_slot_change_is_not_a_legacy_equivalent() -> None:
    """bm25_local sparse (no pre-slots form) or another bge model never matches the old baseline."""
    schema = [_field("author", semantic=True)]
    legacy = _legacy("bge_server", {"base_url": "http://bge:80", "model": "bge-m3"})
    baseline = _pre_slots_signature(legacy, schema)
    bm25 = _migrated(legacy)
    bm25["nodes"][0]["config"]["sparse"] = {"kind": "bm25_local"}
    assert baseline not in CollectionIndexSignature.candidates(bm25, schema)
    other_model = _migrated(_legacy("bge_server", {"base_url": "http://bge:80", "model": "x"}))
    assert baseline not in CollectionIndexSignature.candidates(other_model, schema)


def test_slot_policy_keys_never_move_the_signature() -> None:
    """A key/timeout/retry edit inside a slot leaves the vector space (and signature) unchanged."""
    schema: list = []
    base = _migrated(_legacy("bge_server", {"base_url": "http://bge:80"}))
    tuned = copy.deepcopy(base)
    tuned["nodes"][0]["config"]["dense"].update({"api_key": "k2", "max_retries": 9})
    assert CollectionIndexSignature.compute(base, schema) == CollectionIndexSignature.compute(
        tuned, schema
    )
