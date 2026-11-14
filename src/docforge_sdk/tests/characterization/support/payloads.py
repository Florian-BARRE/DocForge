# ====== Code Summary ======
# Deterministic payload synthesis from a pydantic model's JSON schema, for the model round-trip
# characterization. Two payloads per model: ``full`` (every property filled) and ``minimal`` (only the
# required ones). The synthesis is a pure function of the schema, so a model whose fields, types,
# required-ness or constraints change produces a different golden. No randomness, no clock.

# ====== Standard Library Imports ======
from typing import Any

_DATE_TIME = "2026-01-02T03:04:05Z"
_UUID = "99999999-9999-9999-9999-999999999999"
_MAX_REF_DEPTH = 2  # how many times one $ref may nest into itself before the recursion is cut


class PayloadSynthesizer:
    """
    Builds a JSON-compatible payload that satisfies a model's JSON schema.

    Attributes:
        full (bool): Fill every property (True) or only the required ones (False).
    """

    def __init__(self, schema: dict[str, Any], full: bool) -> None:
        """
        Args:
            schema (dict[str, Any]): The model's ``model_json_schema()`` (with its ``$defs``).
            full (bool): Fill optional properties too.
        """
        self._defs: dict[str, Any] = schema.get("$defs", {})
        self._root = schema
        self.full = full

    def build(self) -> Any:
        """Synthesise the payload of the root schema."""
        return self._value(self._root, [])

    def _value(self, schema: dict[str, Any], stack: list[str]) -> Any:
        """Synthesise one value; ``stack`` holds the $refs being expanded (recursion guard)."""
        # 1. References: resolve, and cut a self-nesting recursion by falling back to an empty node.
        if "$ref" in schema:
            name = schema["$ref"].rsplit("/", 1)[-1]
            if stack.count(name) >= _MAX_REF_DEPTH:
                return {}
            return self._value(self._defs[name], [*stack, name])
        # 2. Fixed values.
        if "const" in schema:
            return schema["const"]
        if "enum" in schema:
            return schema["enum"][0]
        # 3. Unions: the first non-null branch, so an optional field is exercised with a real value.
        for key in ("anyOf", "oneOf"):
            if key in schema:
                branches = [b for b in schema[key] if b.get("type") != "null"]
                return self._value(branches[0], stack) if branches else None
        if "allOf" in schema:
            return self._value(schema["allOf"][0], stack)
        return self._typed(schema, stack)

    def _typed(self, schema: dict[str, Any], stack: list[str]) -> Any:
        """Synthesise a value from a ``type`` keyword (absent type = ``Any`` → a string)."""
        kind = schema.get("type")
        if kind == "string":
            return self._string(schema)
        if kind == "integer":
            return (
                int(
                    schema.get(
                        "minimum",
                        0 if "exclusiveMinimum" not in schema else schema["exclusiveMinimum"] + 1,
                    )
                )
                or 1
            )
        if kind == "number":
            return float(schema.get("minimum", 0.5)) if schema.get("minimum", 0.5) > 0 else 0.5
        if kind == "boolean":
            return True
        if kind == "null":
            return None
        if kind == "array":
            count = max(int(schema.get("minItems", 0)), 1 if self.full else 0)
            return [self._value(schema.get("items", {}), stack) for _ in range(count)]
        if kind == "object":
            return self._object(schema, stack)
        return "value"

    @staticmethod
    def _string(schema: dict[str, Any]) -> str:
        """Synthesise a string honouring ``format`` and ``minLength``."""
        fmt = schema.get("format")
        if fmt == "date-time":
            return _DATE_TIME
        if fmt == "date":
            return "2026-01-02"
        if fmt == "uuid":
            return _UUID
        text = "text"
        return text.ljust(int(schema.get("minLength", 0)), "x")

    def _object(self, schema: dict[str, Any], stack: list[str]) -> dict[str, Any]:
        """Synthesise an object: declared properties, or a free-form/typed map."""
        properties: dict[str, Any] = schema.get("properties", {})
        required = set(schema.get("required", []))
        result = {
            name: self._value(sub, stack)
            for name, sub in properties.items()
            if self.full or name in required
        }
        extra = schema.get("additionalProperties")
        # A free-form map gets one entry when full, or as many as ``minProperties`` demands.
        wanted = max(int(schema.get("minProperties", 0)), 1 if self.full else 0)
        if not properties:
            for index in range(wanted):
                result[f"key{index}"] = (
                    self._value(extra, stack) if isinstance(extra, dict) else "value"
                )
        return result
