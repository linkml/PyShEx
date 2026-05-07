import pytest

from rdflib import Literal, XSD

from pyshex.utils.datatype_utils import total_digits, fraction_digits


def test_total_digits() -> None:
    assert total_digits(Literal(-17)) == 2
    assert total_digits(Literal(17)) == 2
    assert total_digits(Literal(0)) == 1
    assert total_digits(Literal('0.0', datatype=XSD.decimal)) == 1
    assert total_digits(Literal(-0.0, datatype=XSD.decimal)) == 1
    assert total_digits(Literal(1.0, datatype=XSD.decimal)) == 1
    assert total_digits(Literal(-1.0, datatype=XSD.decimal)) == 1
    assert total_digits(Literal(5.55, datatype=XSD.decimal)) == 3
    assert total_digits(Literal('5.55j', datatype=XSD.decimal)) is None
    assert total_digits(Literal('-5.55', datatype=XSD.decimal)) == 3


@pytest.mark.skip(reason="rdflib should never parse 5.55 as an integer, but it does")
def test_total_digits_rdflib_integer_parsing_bug() -> None:
    assert total_digits(Literal(5.55, datatype=XSD.integer)) is None


def test_fraction_digits() -> None:
    assert fraction_digits(Literal(1)) == 0
    assert fraction_digits(Literal(-117253884)) == 0
    assert fraction_digits(Literal(127, datatype=XSD.byte)) == 0
    assert fraction_digits(Literal("Hello")) is None
    assert fraction_digits(Literal(117, datatype=XSD.float)) == 0
    # Note: rdflib creates a type of XSD.double, which is NOT derived from decimal (!)
    assert fraction_digits(Literal(5.0)) == 0
    assert fraction_digits(Literal(5.0, datatype=XSD.decimal)) == 0
    assert fraction_digits(Literal(5.55, datatype=XSD.decimal)) == 2
    assert fraction_digits(Literal('5.55', datatype=XSD.decimal)) == 2
    assert fraction_digits(Literal(-5.0)) == 0
    assert fraction_digits(Literal(-5.0, datatype=XSD.decimal)) == 0
    assert fraction_digits(Literal(-5.55, datatype=XSD.decimal)) == 2
    assert fraction_digits(Literal('-5.55', datatype=XSD.decimal)) == 2
    assert fraction_digits(XSD.decimal) is None
    assert fraction_digits(Literal('abc', datatype=XSD.decimal)) is None