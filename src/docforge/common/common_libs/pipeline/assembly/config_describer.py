# ====== Code Summary ======
# Recursive, schema-driven config describer — the single source for the discovery UI's full
# config tree. `describe(model_cls, cfg)` walks a Pydantic model's JSON schema (+ $defs) and emits
# a nested `ConfigNodeDict` tree (path/kind-tagged) covering EVERY field: gates, atomic toggles,
# search retrieve/grouping/mmr, query_transform, rerank, and the provider unions (chains + single)
# that the schema CANNOT describe (typed `Any`/`list[Any]`) but the registry CAN.
#
# Two glue points, both tiny and explicit:
#   1. _FIELD_CATEGORY_MAP — (ModelName, field_name) → registry category, for the `Any`-typed
#      provider fields. A `list[Any]` field becomes a `chain` node, a scalar `Any` becomes a
#      `provider_union` (optionally `optional`). Choices come from `get_configs(category)` using
#      the cheap selectable() hook only (structural defaults; merge_defaults not applied — per-collection);
#      each choice's `params` are produced by RECURSING describe() on the provider config class.
#   2. auto_import of all categories (incl. llm + rerank) before walking, so @register fires.
#
# I/O-FREE BY CONTRACT: this is a config-FORM describer, NOT a monitoring surface. It performs NO
# network probes — provider `availability()` hooks do a blocking ~1s socket probe per provider, and
# the recursive walk re-describes the embed providers ~3× (embed.chain + embed.sparse + semantic.embed),
# so probing made GET /discovery take ~45s. Choices therefore report `available=True` unconditionally;
# whether a service is currently UP is a separate concern owned by /monitoring/resources. Only the
# cheap, non-I/O `selectable()` hook (e.g. vit_onnx's model_path check) still gates UI choices.
#
# Emits plain dicts (ConfigNodeDict) — the backend's Pydantic ConfigNode validates them at the
# router boundary. Keeping this in common_libs avoids the layer DAG depending on the app's models.
#
# DescribeSurface (describe.py) stays as the FLAT surface (dynamic_fields); this is its recursive
# sibling. They share _scalar_ui_type and the _is_secret_key convention.

# ====== Standard Library Imports ======
from __future__ import annotations

import copy
from typing import Any

# ====== Internal Project Imports ======
from common_libs.config.pipeline import _is_secret_key

# ====== Local Project Imports ======
from .describe_helpers import _scalar_ui_type

# A described node, emitted as a plain dict (validated by the backend's ConfigNode model).
ConfigNodeDict = dict[str, Any]

# (Pydantic model class name, field name) → registry category. The ONLY hand-authored glue:
# these are the `Any` / `list[Any]` provider fields the JSON schema cannot describe. A field whose
# annotation is a list becomes a `chain` node; a scalar `Any` becomes a `provider_union` node.
_FIELD_CATEGORY_MAP: dict[tuple[str, str], str] = {
    ("ParseConfig", "chain"): "parser",
    ("EnrichConfig", "classifier_chain"): "classifier",
    ("EnrichConfig", "ocr_chain"): "ocr",
    ("EnrichConfig", "vlm_chain"): "vlm",
    ("ChunkConfig", "split_method"): "split_method",
    ("SemanticConfig", "embed"): "embed",
    ("EmbedConfig", "chain"): "embed",
    ("EmbedConfig", "sparse"): "embed",
    ("RerankConfig", "chain"): "rerank",
    ("QueryTransformConfig", "llm"): "llm",
}

# Provider categories whose @register decorators must have fired before the walk, so
# get_configs(category) returns every choice. Two correctness notes:
#   * The CANONICAL package root is `common_libs.providers.*`. The legacy describe_stages() list
#     uses `libs.providers.*`, which auto_import() silently swallows (ImportError) — those configs
#     only end up registered as a side effect of stage configs' lazy validation imports. This
#     describer must be self-sufficient, so it imports via the path that actually resolves.
#   * describe_stages() omits llm + rerank (they are search-only); the recursive describer needs
#     them for SearchConfig's nested unions, so they are explicitly included here.
_AUTO_IMPORT_PACKAGES: tuple[str, ...] = (
    "common_libs.providers.converter",
    "common_libs.providers.parser",
    "common_libs.providers.classifier",
    "common_libs.providers.ocr",
    "common_libs.providers.vlm",
    "common_libs.providers.embed",
    "common_libs.providers.rerank",
    "common_libs.providers.llm",
)


class ConfigDescriberHelpers:
    """
    Static-only recursive describer building the discovery config tree from a Pydantic model.

    Read-only relative to all state: it queries provider configs (the cheap selectable hook,
    structural defaults) and JSON schemas but mutates nothing, and performs NO network I/O. The
    host passes the RUNTIME_CONFIG instance (``cfg``) used for the selectable hook — mirroring
    DescribeSurface, which reads ``registry._cfg``.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:
        """Block instantiation — this is a static-only helper class."""
        raise TypeError(f"{cls.__name__} is a static-only class and cannot be instantiated.")

    # ─── Public entry point ─────────────────────────────────────────────────────

    @classmethod
    def describe(cls, model_cls: type, cfg: Any, root_path: str = "pipeline") -> ConfigNodeDict:
        """
        Describe a Pydantic model as a recursive ``object`` ConfigNode tree.

        Args:
            model_cls (type): A Pydantic BaseModel subclass (e.g. ``PipelineConfig``).
            cfg (Any): RUNTIME_CONFIG instance — used for provider availability (merge_defaults not applied — provider config is per-collection).
            root_path (str): Absolute dot-path prefix for the root node (default ``"pipeline"``).

        Returns:
            ConfigNodeDict: The root object node with fully recursed ``children``.
        """
        # 1. Ensure every provider category is registered before any union is walked. Idempotent
        #    and process-cached: @register fires once and stays, so the (filesystem-walking)
        #    auto_import never re-runs — critically, NOT on every recursive describe() entry.
        cls._ensure_registered()

        # 2. Walk the model's schema into a single object node rooted at root_path.
        schema = model_cls.model_json_schema()
        defs = schema.get("$defs", {})
        return cls._object_node(
            path=root_path,
            label=cls._label_from(schema, model_cls.__name__),
            description=schema.get("description", ""),
            model_name=model_cls.__name__,
            properties=schema.get("properties", {}),
            defs=defs,
        )

    # ─── Registration bootstrap ─────────────────────────────────────────────────

    @classmethod
    def _ensure_registered(cls) -> None:
        """
        Run provider auto-import exactly once per process (idempotent, filesystem-cheap thereafter).

        ``@register`` is a permanent, process-global side effect of importing a provider module, so
        re-walking the packages on every (recursive) ``describe()`` call is pure waste —
        ``auto_import`` does a ``pkgutil.walk_packages`` filesystem scan that dominated the build
        time (~6 s/call × the recursive entries). The guard collapses that to a single first walk.
        """
        # 1. Already imported in this process → nothing to do (the registry is permanent).
        if cls._registered:
            return
        # 2. First call: walk every provider package + the chunking strategies once.
        cls._auto_import_all()
        cls._registered = True

    @staticmethod
    def _auto_import_all() -> None:
        """Trigger @register for every provider category (incl. llm + rerank) and split_method."""
        from common_libs.config.pipeline._registry import auto_import

        for pkg in _AUTO_IMPORT_PACKAGES:
            auto_import(pkg)
        # split_method configs register on import of the chunking strategies package.
        import common_libs.pipeline.stages.s4_chunk as _chunking_pkg  # noqa: F401

    # ─── Object / property walk ─────────────────────────────────────────────────

    @classmethod
    def _object_node(
        cls,
        path: str,
        label: str,
        description: str,
        model_name: str,
        properties: dict[str, Any],
        defs: dict[str, Any],
    ) -> ConfigNodeDict:
        """
        Build a ``kind=object`` node by recursing every property into a child node.

        Args:
            path (str): Absolute dot-path of this object.
            label (str): Human-readable label.
            description (str): Tooltip text.
            model_name (str): Owning Pydantic model name (drives the field→category lookup).
            properties (dict): The model's JSON-schema ``properties`` block.
            defs (dict): The root schema's ``$defs`` (shared across the whole walk).

        Returns:
            ConfigNodeDict: The object node with its recursed children.
        """
        children: list[ConfigNodeDict] = []
        for name, prop in properties.items():
            # The discriminator field is internal plumbing, never a user knob.
            if name == "id":
                continue
            child = cls._field_node(
                parent_path=path, model_name=model_name, field_name=name, prop=prop, defs=defs
            )
            if child is not None:
                children.append(child)
        return {
            "path": path,
            "kind": "object",
            "label": label,
            "description": description,
            "children": children,
        }

    @classmethod
    def _field_node(
        cls,
        parent_path: str,
        model_name: str,
        field_name: str,
        prop: dict[str, Any],
        defs: dict[str, Any],
    ) -> ConfigNodeDict | None:
        """
        Dispatch one field to the right node builder (provider union > object > enum > scalar).

        Args:
            parent_path (str): Dot-path of the owning object.
            model_name (str): Owning model name (for the field→category lookup).
            field_name (str): The field name.
            prop (dict): The field's JSON-schema property.
            defs (dict): Shared ``$defs``.

        Returns:
            ConfigNodeDict | None: The child node, or None when the field is not renderable.
        """
        path = f"{parent_path}.{field_name}"

        # 1. Provider union (the schema can't describe it — the registry can).
        category = _FIELD_CATEGORY_MAP.get((model_name, field_name))
        if category is not None:
            return cls._provider_node(path, prop, category, defs)

        # 2. Enum (Literal) → enum node.
        options = cls._enum_options(prop, defs)
        if options is not None:
            return cls._enum_node(path, field_name, prop, options)

        # 3. Nested object ($ref / inline) → recurse its properties.
        obj_schema, obj_name = cls._resolve_object(prop, defs)
        if obj_schema is not None:
            return cls._object_node(
                path=path,
                label=cls._label_from(prop, field_name),
                description=prop.get("description", ""),
                model_name=obj_name,
                properties=obj_schema.get("properties", {}),
                defs=defs,
            )

        # 4. Scalar → scalar node (None when not a single-control scalar, e.g. list[obj]/dict).
        scalar = _scalar_ui_type(prop)
        if scalar is not None:
            return cls._scalar_node(path, field_name, prop, scalar)

        # 5. Not renderable as a single control (e.g. heading_rules list, field_weights map).
        return None

    # ─── Leaf builders ──────────────────────────────────────────────────────────

    @classmethod
    def _scalar_node(cls, path: str, field_name: str, prop: dict[str, Any], scalar: str) -> ConfigNodeDict:
        """Build a ``kind=scalar`` node, masking credential-named fields as ``secret``."""
        ui_type = "secret" if scalar == "str" and _is_secret_key(field_name) else scalar
        node: ConfigNodeDict = {
            "path": path,
            "kind": "scalar",
            "label": cls._label_from(prop, field_name),
            "description": prop.get("description", ""),
            "default": prop.get("default"),
            "type": ui_type,
        }
        # Bounds come straight from the schema (ge/le → minimum/maximum), incl. Optional branches.
        minimum, maximum = cls._numeric_bounds(prop)
        if minimum is not None:
            node["min"] = minimum
        if maximum is not None:
            node["max"] = maximum
        return node

    @classmethod
    def _enum_node(cls, path: str, field_name: str, prop: dict[str, Any], options: list[Any]) -> ConfigNodeDict:
        """Build a ``kind=enum`` node from a Literal/enum field's allowed values."""
        return {
            "path": path,
            "kind": "enum",
            "label": cls._label_from(prop, field_name),
            "description": prop.get("description", ""),
            "default": prop.get("default"),
            "options": options,
        }

    # ─── Provider union (chain / provider_union) ────────────────────────────────

    @classmethod
    def _provider_node(cls, path: str, prop: dict[str, Any], category: str, defs: dict[str, Any]) -> ConfigNodeDict:
        """
        Build a ``chain`` (list) or ``provider_union`` (single) node from the registry.

        A ``list[Any]`` field → ``kind=chain`` (multi=True). A scalar ``Any`` field →
        ``kind=provider_union`` (multi=False); a field that admits None (no required default,
        or a ``null`` anyOf branch) is marked ``optional`` so the UI can offer "disabled".

        Args:
            path (str): Absolute dot-path of the field.
            prop (dict): The field's JSON-schema property.
            category (str): Registry category (parser/embed/rerank/llm/…).
            defs (dict): Shared ``$defs`` (passed to the recursive describe of each choice).

        Returns:
            ConfigNodeDict: The chain / provider_union node with recursed choices.
        """
        is_list = cls._is_list(prop)
        kind = "chain" if is_list else "provider_union"
        node: ConfigNodeDict = {
            "path": path,
            "kind": kind,
            "label": cls._label_from(prop, path.rsplit(".", 1)[-1]),
            "description": prop.get("description", ""),
            "multi": is_list,
            "optional": (not is_list) and cls._is_optional(prop),
            "capability": category,
            "choices": cls._provider_choices(category, defs),
        }
        return node

    @classmethod
    def _provider_choices(cls, category: str, defs: dict[str, Any]) -> list[ConfigNodeDict]:
        """
        Build the choice list for a category, RECURSING describe() on each provider config.

        Performs NO network I/O. The flat DescribeSurface._auto_providers probes each provider's
        ``availability(cfg)`` hook (a blocking ~1s socket connect) — this config-FORM describer does
        NOT: a form lists what is *configurable*, while whether a service is currently reachable is a
        live-monitoring concern owned by /monitoring/resources. So every choice reports
        ``available=True`` and only the cheap, non-I/O ``selectable()`` hook gates UI offering.

        NOTE: unlike the flat surface this surfaces STRUCTURAL defaults from the provider class
        schema — merge_defaults(cfg) is NOT applied (provider config is per-collection, so it is a
        no-op today; if a future provider derives a default from cfg, wire merge_defaults here).
        Each choice's ``params`` is the recursively-described field list of that provider config
        (so a nested union — semantic.embed — is expressible). The per-class recursive describe is
        memoized for the duration of one build (see ``_describe_provider``) so an embed provider
        re-encountered under embed.chain / embed.sparse / semantic.embed is only walked once.

        Args:
            category (str): Registry category.
            defs (dict): Unused at this depth (each provider model emits its own $defs) — kept
                for signature symmetry with the object walk.

        Returns:
            list[ConfigNodeDict]: One ProviderChoice dict per registered provider.
        """
        from common_libs.config.pipeline._registry import get_configs

        _ = defs
        choices: list[ConfigNodeDict] = []
        for config_cls in get_configs(category).values():
            selectable = cls._selectable(config_cls)
            # The choice's own fields are the recursively-described provider config — its
            # children become the choice's `params` (a nested union recurses naturally). Memoized
            # per class so the embed providers (walked 3× across the tree) are described once.
            params = cls._describe_provider(config_cls)
            choices.append({
                "id": config_cls.model_fields["id"].default,
                "label": getattr(config_cls, "_label", config_cls.__name__),
                # Config-form describer: never live-probed. UP/DOWN is a /monitoring/resources concern.
                "available": True,
                "selectable": selectable,
                # `default` is not tracked at the registry level (the flat _auto_providers surface
                # omits it too); the frontend derives the default from the empty-chain behaviour.
                "default": False,
                "note": "",
                "params": params,
            })
        return choices

    # ─── Provider introspection (cheap, non-I/O) ────────────────────────────────

    @classmethod
    def _describe_provider(cls, config_cls: type) -> list[ConfigNodeDict]:
        """
        Recursively describe a provider config's own fields as a choice's ``params`` (memoized).

        The recursive walk re-encounters the embed providers three times (embed.chain,
        embed.sparse, semantic.embed). Memoizing the per-class result within one build means each
        provider's schema is walked exactly once. A deep copy is returned on a cache hit so the
        caller's path-reparenting never mutates the shared cached node.

        Args:
            config_cls (type): The provider's Pydantic config class.

        Returns:
            list[ConfigNodeDict]: The provider's described fields (paths local, leading "." stripped).
        """
        # 1. Serve a deep copy from cache so reparenting/mutation stays caller-local.
        cached = cls._describe_cache.get(config_cls)
        if cached is not None:
            return copy.deepcopy(cached)
        # 2. Describe once: recurse the provider model, then strip the synthetic empty root path.
        described = cls.describe(config_cls, cls._cfg_for(config_cls), root_path="")
        params = cls._reparent_params(path_prefix="", children=described["children"])
        # 3. Cache the canonical result; hand the caller its own copy.
        cls._describe_cache[config_cls] = params
        return copy.deepcopy(params)

    @classmethod
    def _selectable(cls, config_cls: type) -> bool:
        """Honor the optional ``selectable(cfg)`` hook (most providers are always selectable)."""
        hook = getattr(config_cls, "selectable", None)
        if not callable(hook):
            return True
        try:
            return bool(hook(cls._runtime_cfg))
        except Exception:
            return False

    @classmethod
    def _cfg_for(cls, config_cls: type) -> Any:
        """Return the runtime config used when recursing a provider's own fields."""
        _ = config_cls
        return cls._runtime_cfg

    # ─── Schema helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _reparent_params(path_prefix: str, children: list[ConfigNodeDict]) -> list[ConfigNodeDict]:
        """
        Strip the synthetic empty root path from a provider's described children.

        A provider config is described with ``root_path=""`` so its children carry paths like
        ``".base_url"``; the leading dot is removed so a choice's params read as local field
        names the frontend prefixes when a choice is picked.

        Args:
            path_prefix (str): Unused prefix (kept for future absolute-path reparenting).
            children (list[ConfigNodeDict]): The provider object's children.

        Returns:
            list[ConfigNodeDict]: Children with the leading "." trimmed from every path (deep).
        """
        _ = path_prefix

        def _strip(node: ConfigNodeDict) -> ConfigNodeDict:
            node["path"] = node["path"].lstrip(".")
            for grandchild in node.get("children", []):
                _strip(grandchild)
            for choice in node.get("choices", []):
                for param in choice.get("params", []):
                    _strip(param)
            return node

        return [_strip(c) for c in children]

    @staticmethod
    def _branches(prop: dict[str, Any]) -> list[dict[str, Any]]:
        """Return the anyOf/oneOf branches of a property (empty list when none)."""
        return [*prop.get("anyOf", []), *prop.get("oneOf", [])]

    @classmethod
    def _is_optional(cls, prop: dict[str, Any]) -> bool:
        """True when the field admits ``null`` (a null branch) or carries a None default."""
        if any(b.get("type") == "null" for b in cls._branches(prop)):
            return True
        return prop.get("default", "__missing__") is None

    @classmethod
    def _is_list(cls, prop: dict[str, Any]) -> bool:
        """True when the field (or an anyOf branch) is an array."""
        if prop.get("type") == "array":
            return True
        return any(b.get("type") == "array" for b in cls._branches(prop))

    @classmethod
    def _enum_options(cls, prop: dict[str, Any], defs: dict[str, Any]) -> list[Any] | None:
        """
        Extract enum/Literal options from a property, resolving a single $ref enum if needed.

        Args:
            prop (dict): The field property.
            defs (dict): Shared ``$defs`` (a Literal may be lifted to a $def enum).

        Returns:
            list[Any] | None: The allowed values, or None when the field is not an enum.
        """
        # 1. Direct enum on the property.
        if "enum" in prop:
            return list(prop["enum"])
        # 2. A $ref to a $def that is an enum.
        ref = prop.get("$ref")
        if isinstance(ref, str):
            target = defs.get(ref.rsplit("/", 1)[-1], {})
            if "enum" in target:
                return list(target["enum"])
        # 3. An anyOf/oneOf whose non-null branch is an enum (Optional[Literal[...]]).
        for branch in cls._branches(prop):
            if "enum" in branch:
                return list(branch["enum"])
        return None

    @classmethod
    def _resolve_object(cls, prop: dict[str, Any], defs: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """
        Resolve a property to its nested-object schema + model name, or (None, "") when not an object.

        Handles a direct ``$ref``, an inline ``type=object`` with ``properties``, and an
        ``anyOf``/``oneOf`` whose non-null branch is an object ref.

        Args:
            prop (dict): The field property.
            defs (dict): Shared ``$defs``.

        Returns:
            tuple[dict | None, str]: (object schema, model name), or (None, "").
        """
        # 1. Direct $ref into $defs.
        ref = prop.get("$ref")
        if isinstance(ref, str):
            name = ref.rsplit("/", 1)[-1]
            target = defs.get(name, {})
            if "properties" in target:
                return target, name
            return None, ""
        # 2. Inline object with properties.
        if prop.get("type") == "object" and "properties" in prop:
            return prop, prop.get("title", "")
        # 3. anyOf/oneOf with an object $ref branch (e.g. Optional[SomeModel]).
        for branch in cls._branches(prop):
            sub_ref = branch.get("$ref")
            if isinstance(sub_ref, str):
                name = sub_ref.rsplit("/", 1)[-1]
                target = defs.get(name, {})
                if "properties" in target:
                    return target, name
        return None, ""

    @classmethod
    def _numeric_bounds(cls, prop: dict[str, Any]) -> tuple[Any, Any]:
        """
        Extract (minimum, maximum) from a property, including its anyOf/oneOf scalar branch.

        Args:
            prop (dict): The field property.

        Returns:
            tuple[Any, Any]: (minimum, maximum) — each None when absent.
        """
        minimum = prop.get("minimum")
        maximum = prop.get("maximum")
        if minimum is None and maximum is None:
            for branch in cls._branches(prop):
                if "minimum" in branch or "maximum" in branch:
                    return branch.get("minimum"), branch.get("maximum")
        return minimum, maximum

    @staticmethod
    def _label_from(schema: dict[str, Any], fallback: str) -> str:
        """Return a human label from a schema's ``title`` (or a Title-cased field name)."""
        return schema.get("title") or fallback.replace("_", " ").title()

    # The runtime config used for the selectable hook — set per-describe() via the public API.
    _runtime_cfg: Any = None

    # Process-global guard: provider auto-import (a permanent @register side effect that does a
    # costly filesystem package-walk) runs once, not on every recursive describe() entry.
    _registered: bool = False

    # Per-build memoization of the recursive per-provider describe (class → described params).
    # Reset at the start of every top-level build by the module-level describe() entry point, so a
    # provider re-encountered across the tree (embed.chain / embed.sparse / semantic.embed) is
    # walked once per request without leaking described state between requests.
    _describe_cache: dict[type, list[ConfigNodeDict]] = {}


def describe(model_cls: type, cfg: Any, root_path: str = "pipeline") -> ConfigNodeDict:
    """
    Describe a Pydantic model as a recursive ConfigNode tree (module-level entry point).

    Args:
        model_cls (type): A Pydantic BaseModel subclass (e.g. ``PipelineConfig``).
        cfg (Any): RUNTIME_CONFIG instance — used for provider availability (merge_defaults not applied — provider config is per-collection).
        root_path (str): Absolute dot-path prefix for the root node (default ``"pipeline"``).

    Returns:
        ConfigNodeDict: The recursively-described config tree (plain dicts).
    """
    # 1. Stash the runtime config so the static helper's selectable hook can read it without
    #    threading it through every recursive call — describe() is single-threaded per request.
    ConfigDescriberHelpers._runtime_cfg = cfg
    # 2. Reset the per-build provider memo so no described state leaks between requests. Done here
    #    (the true public entry), NOT in the recursive class method which re-enters per provider.
    ConfigDescriberHelpers._describe_cache = {}
    # 3. Walk the model into the recursive config tree.
    return ConfigDescriberHelpers.describe(model_cls, cfg, root_path=root_path)


__all__ = ["describe", "ConfigDescriberHelpers", "ConfigNodeDict"]
