"""Preserve the written lexical form of *bare* Turtle/N3 numerics.

``rdflib.NORMALIZE_LITERALS = False`` (set in :mod:`pyshex`) keeps quoted literals
as written, but rdflib's N3/Turtle tokenizer round-trips unquoted numerics through
``int()`` / ``Decimal()`` before ``normalise`` rebuilds the Literal from ``str()``,
so ``<p> 00`` reaches the graph as ``"0"^^xsd:integer`` and its (non-canonical, but
validation-relevant) lexical form is unrecoverable.  ``long_type`` and ``Decimal``
are notation3 module globals used only to build and type-check those tokens, so
lexical-carrying subclasses restore fidelity without touching any parser method.
"""
from decimal import Decimal

from rdflib.plugins.parsers import notation3


class _LexicalInt(int):
    """An int that remembers -- and stringifies to -- the lexical form it came from."""
    def __new__(cls, lexical):
        self = super().__new__(cls, lexical)
        self._lexical = str(lexical)
        return self

    def __str__(self) -> str:
        return self._lexical


class _LexicalDecimal(Decimal):
    """A Decimal that remembers -- and stringifies to -- the lexical form it came from."""
    def __new__(cls, lexical):
        self = super().__new__(cls, lexical)
        self._lexical = str(lexical)
        return self

    def __str__(self) -> str:
        return self._lexical


def install() -> None:
    notation3.long_type = _LexicalInt
    notation3.Decimal = _LexicalDecimal
