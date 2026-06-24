# ====== Code Summary ======
# Static helpers for the inference router. Provides input normalization shared by the
# /embed and /embed_sparse routes. Per-request tracing logs live in router.py (bound to
# "InferenceRouter") where the batch size is known; no logger is needed here.


class InferenceHelpers:
    """
    Static utility helpers for the BGE inference router.

    Handles input normalization shared across the /embed and /embed_sparse routes.
    Per-request tracing is done in router.py where the full request context is available.
    """

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError(f"InferenceHelpers is a static-only class and cannot be instantiated.")

    @staticmethod
    def as_list(inputs: list[str] | str) -> list[str]:
        """
        Normalize the TEI ``inputs`` field (str or list[str]) into a plain list of texts.

        TEI accepts either a single string or a batch list — both must produce identical
        downstream behaviour. This normalization step ensures the model service always
        receives a list.

        Args:
            inputs (list[str] | str): Raw ``inputs`` value from the request body.

        Returns:
            list[str]: A list containing the input text(s).
        """
        return [inputs] if isinstance(inputs, str) else list(inputs)
