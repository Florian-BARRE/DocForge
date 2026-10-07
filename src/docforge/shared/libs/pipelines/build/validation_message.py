# ====== Code Summary ======
# ValidationMessage — renders a pydantic ValidationError raised while validating a node config or a
# pipeline blob into a stable, INPUT-FREE human message. ``str(ValidationError)`` embeds
# ``input_value=…`` for every error, and for a missing field or a model-level error that value is the
# WHOLE config dict — which, on every write path, carries the restored real provider secret. Every
# error path that wraps a config/blob validation failure into text (build errors, drift errors, logs)
# formats it through here, so a secret can never ride out in a response body or a log line.

# ====== Third-Party Library Imports ======
from pydantic import ValidationError


class ValidationMessage:
    """Static formatter of a pydantic ValidationError without its input values."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("ValidationMessage is a static-only class and cannot be instantiated.")

    @staticmethod
    def format(exc: ValidationError) -> str:
        """
        Render ``exc`` as ``"<n> validation error(s): <loc>: <msg>; …"`` — never the input.

        Args:
            exc (ValidationError): The error raised validating a config / blob.

        Returns:
            str: One clause per error (location + message), with no input value, URL or context.
        """
        # 1. Ask pydantic for the structured errors with every input-bearing part stripped.
        errors = exc.errors(include_input=False, include_url=False, include_context=False)

        # 2. One "loc: msg" clause per error; a model-level error has an empty location.
        clauses = [
            f"{'.'.join(str(part) for part in error.get('loc', ())) or '<root>'}: {error.get('msg')}"
            for error in errors
        ]
        return f"{len(errors)} validation error(s): " + "; ".join(clauses)


__all__ = ["ValidationMessage"]
