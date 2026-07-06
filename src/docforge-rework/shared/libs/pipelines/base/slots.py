# ====== Code Summary ======
# SlotTypes — the ONE reading of what a CONSUMES/PRODUCES slot annotation is allowed to be: a plain
# artefact class, or a list of one artefact class (what a ForEach consumes and produces). Shared by
# the node contract (definition-time enforcement), describe() (the UI label) and the validator
# (type compatibility), so the three can never drift apart.

# ====== Standard Library Imports ======
from types import UnionType
from typing import Union, get_args, get_origin


class SlotTypes:
    """Static reading of slot annotations — pure, no side effects."""

    def __new__(cls, *args: object, **kwargs: object) -> None:
        raise TypeError("SlotTypes is a static-only class and cannot be instantiated.")

    @classmethod
    def element(cls, annotation: object) -> tuple[type | None, bool]:
        """
        Decompose a slot annotation.

        Args:
            annotation (object): The field annotation of an I/O model.

        Returns:
            tuple[type | None, bool]: (the element class, is_list). (None, False) when the
            annotation is not a plain class, ``list[Class]``, or an optional (``X | None``)
            of either — the only valid slot shapes.
        """
        # 1. A plain artefact class.
        if isinstance(annotation, type):
            return annotation, False
        # 2. list[Class] — exactly one, non-generic element type.
        if get_origin(annotation) is list:
            args = get_args(annotation)
            if len(args) == 1 and isinstance(args[0], type):
                return args[0], True
        # 3. X | None — an OPTIONAL slot: unwrap and read the element as usual (the
        #    optionality itself is carried by the field's default → IoSlot.required).
        if get_origin(annotation) in (UnionType, Union):
            inner = [arg for arg in get_args(annotation) if arg is not type(None)]
            if len(inner) == 1:
                return cls.element(inner[0])
        return None, False

    @classmethod
    def label(cls, annotation: object) -> str:
        """The UI/describe label of a slot annotation ('Doc' or 'list[Doc]')."""
        element, is_list = cls.element(annotation)
        if element is None:
            return str(annotation)
        return f"list[{element.__name__}]" if is_list else element.__name__


__all__ = ["SlotTypes"]
