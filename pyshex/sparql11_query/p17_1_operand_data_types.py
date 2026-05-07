from typing import cast

from rdflib import Literal, XSD, URIRef, BNode
from rdflib.term import Node


def is_typed_literal(n: Node) -> bool:
    return isinstance(n, Literal) and n.datatype is not None


def is_plain_literal(n: Node) -> bool:
    return isinstance(n, Literal) and n.datatype is None


def is_strict_numeric(n: Node) -> bool:
    """ numeric denotes typed literals with datatypes xsd:integer, xsd:decimal, xsd:float, and xsd:double. """
    return is_typed_literal(n) and cast(Literal, n).datatype in [XSD.integer, XSD.decimal, XSD.float, XSD.double]


def is_simple_literal(n: Node) -> bool:
    """ simple literal denotes a plain literal with no language tag. """
    return is_typed_literal(n) and cast(Literal, n).datatype is None and cast(Literal, n).language is None


def is_rdf_term(n: Node) -> bool:
    return isinstance(n, (URIRef, Literal, BNode))


def is_integer(n: Node) -> bool:
    return is_typed_literal(n) and cast(Literal, n).datatype in [
        XSD.integer,
        XSD.nonPositiveInteger,
        XSD.negativeInteger,
        XSD.long,
        XSD.int,
        XSD.short,
        XSD.byte,
        XSD.nonNegativeInteger,
        XSD.unsignedLong,
        XSD.unsignedInt,
        XSD.unsignedShort,
        XSD.unsignedByte,
        XSD.positiveInteger
    ]


def is_decimal(n: Node) -> bool:
    return is_integer(n) or (is_typed_literal(n) and cast(Literal, n).datatype in [XSD.decimal])


def is_numeric(n: Node) -> bool:
    return is_decimal(n) or (is_typed_literal(n) and cast(Literal, n).datatype in [XSD.float, XSD.double])


def is_sparql_operand_datatype(n: Node | str) -> bool:
    # From: https://www.w3.org/TR/sparql11-query/#operandDataTypes
    if isinstance(n, str):
        n = URIRef(n)
    return is_plain_literal(n) or (is_typed_literal(n) and cast(Literal, n).datatype in [
        XSD.integer,
        XSD.decimal,
        XSD.float,
        XSD.double,
        XSD.string,
        XSD.boolean,
        XSD.dateTime,
        XSD.nonPositiveInteger,
        XSD.negativeInteger,
        XSD.long,
        XSD.int,
        XSD.short,
        XSD.byte,
        XSD.nonNegativeInteger,
        XSD.unsignedLong,
        XSD.unsignedInt,
        XSD.unsignedShort,
        XSD.unsignedByte,
        XSD.positiveInteger
    ])
