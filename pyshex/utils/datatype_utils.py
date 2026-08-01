import re

import jsonasobj
from ShExJSG import ShExJ
from pyjsg.jsglib import JSGString, JSGObject
from rdflib import Literal, XSD

from pyshex.sparql11_query.p17_1_operand_data_types import is_integer


def can_cast_to(v: Literal, dt: str) -> bool:
    """ 5.4.3 Datatype Constraints

    Determine whether "a value of the lexical form of n can be cast to the target type v per
    XPath Functions 3.1 section 19 Casting[xpath-functions]."
    """
    # TODO: rdflib doesn't appear to pay any attention to lengths (e.g. 257 is a valid XSD.byte)
    return v.value is not None and Literal(str(v), datatype=dt).value is not None


# XSD 1.1 lexical spaces (with XSD 1.0's INF spelling -- no "+INF" -- per the test suite)
_INTEGER_LEX = re.compile(r'[+-]?[0-9]+')
_DECIMAL_LEX = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)')
_FLOAT_LEX = re.compile(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?|-?INF|NaN')
_BOOLEAN_LEX = re.compile(r'true|false|1|0')
_DATETIME_LEX = re.compile(r'-?[0-9]{4,}-[0-9]{2}-[0-9]{2}'
                           r'T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?'
                           r'(?:Z|[+-][0-9]{2}:[0-9]{2})?')

# value ranges of the integer-derived types (lexical space is _INTEGER_LEX for all)
_INTEGER_RANGES: dict[str, tuple[int | None, int | None]] = {
    'integer': (None, None),
    'nonPositiveInteger': (None, 0),
    'negativeInteger': (None, -1),
    'long': (-2 ** 63, 2 ** 63 - 1),
    'int': (-2 ** 31, 2 ** 31 - 1),
    'short': (-2 ** 15, 2 ** 15 - 1),
    'byte': (-2 ** 7, 2 ** 7 - 1),
    'nonNegativeInteger': (0, None),
    'positiveInteger': (1, None),
    'unsignedLong': (0, 2 ** 64 - 1),
    'unsignedInt': (0, 2 ** 32 - 1),
    'unsignedShort': (0, 2 ** 16 - 1),
    'unsignedByte': (0, 2 ** 8 - 1),
}

_LEXICAL_SPACES: dict[str, re.Pattern] = {
    **{local: _INTEGER_LEX for local in _INTEGER_RANGES},
    'decimal': _DECIMAL_LEX,
    'float': _FLOAT_LEX,
    'double': _FLOAT_LEX,
    'boolean': _BOOLEAN_LEX,
    'dateTime': _DATETIME_LEX,
}


def is_valid_lexical_form(n: Literal) -> bool | None:
    """Whether n's lexical form belongs to the lexical space of its datatype (including
    the value range for the integer-derived types, which rdflib does not check).
    None means the datatype is not one this function knows how to validate."""
    dt = str(n.datatype)
    xsd_ns = str(XSD)
    if not dt.startswith(xsd_ns):
        return None
    pattern = _LEXICAL_SPACES.get(dt[len(xsd_ns):])
    if pattern is None:
        return None
    lex = str(n)
    if not pattern.fullmatch(lex):
        return False
    lo, hi = _INTEGER_RANGES.get(dt[len(xsd_ns):], (None, None))
    if lo is None and hi is None:
        return True
    value = int(lex)
    return (lo is None or value >= lo) and (hi is None or value <= hi)


def is_decimal_derived(n: Literal) -> bool:
    """Whether n's datatype is xsd:decimal or derived from it -- the only datatypes the
    totaldigits/fractiondigits facets apply to (constraints on others must fail)."""
    if not isinstance(n, Literal):
        return False
    dt = str(n.datatype)
    xsd_ns = str(XSD)
    return dt.startswith(xsd_ns) and (dt[len(xsd_ns):] == 'decimal' or dt[len(xsd_ns):] in _INTEGER_RANGES)


def total_digits(n: Literal) -> int | None:
    """ 5.4.5 XML Schema Numberic Facet Constraints

     totaldigits and fractiondigits constraints on values not derived from xsd:decimal fail.
     """
    return len(str(abs(int(n.value)))) + fraction_digits(n) if is_decimal_derived(n) and n.value is not None else None


def fraction_digits(n: Literal) -> int | None:
    """ 5.4.5 XML Schema Numeric Facet Constraints

    for "fractiondigits" constraints, v is less than or equals the number of digits to the right of the decimal place
    in the XML Schema canonical form[xmlschema-2] of the value of n, ignoring trailing zeros.
    """
    # Note - the last expression below isolates the fractional portion, reverses it (e.g. 017320 --> 023710) and
    #        converts it to an integer and back to a string
    return None if not is_decimal_derived(n) or n.value is None \
        else 0 if is_integer(n) or '.' not in str(n.value) or str(n.value).split('.')[1] == '0' \
        else len(str(int(str(n.value).split('.')[1][::-1])))


def pattern_match(pattern: str, flags: str, val: str) -> bool:
    re_flags, pattern = _map_xpath_flags_to_re(reencode_escapes(pattern), flags)
    return re.search(pattern, val, flags=re_flags) is not None


def reencode_escapes(pattern: str) -> str:
    return re.sub(r'\\.', _subf, pattern)


def _subf(matchobj) -> str:
    o = matchobj.group(0)
    # every regex metacharacter must keep its escape -- dropping it changes the
    # pattern's meaning (an unescaped '|' turns the whole pattern into an alternation)
    return o if o[1] in ['\\', '^', '$', '?', ',', '[', ']', '(', ')', '.', '*', '+', '{', '}', '|', '-'] \
        else '\t' if o[1] == 't' \
        else '\n' if o[1] == 'n' \
        else '\r' if o[1] == 'r' \
        else o[1]


def _map_xpath_flags_to_re(expr: str, xpath_flags: str) -> tuple[int, str]:
    """ Map `5.6.2 Flags <https://www.w3.org/TR/xpath-functions-31/#flags>`_  to python

    :param expr: match pattern
    :param xpath_flags: xpath flags
    :returns: python flags / modified match pattern
    """
    python_flags: int = 0
    modified_expr = expr
    if xpath_flags is None:
        xpath_flags = ""

    if 's' in xpath_flags:
        python_flags |= re.DOTALL
    if 'm' in xpath_flags:
        python_flags |= re.MULTILINE
    if 'i' in xpath_flags:
        python_flags |= re.IGNORECASE
    if 'x' in xpath_flags:
        modified_expr = re.sub(r'[\t\n\r ]|\[[^\]]*\]', _char_class_escape, modified_expr)
    if 'q' in xpath_flags:
        modified_expr = re.escape(modified_expr)

    return python_flags, modified_expr


def _char_class_escape(m) -> str:
    """ regular expression are removed prior to matching with one exception: whitespace characters within character
     class expressions (charClassExpr) are not removed.
     """
    match_str = m.group(0)
    return match_str if match_str[0] == '[' and match_str[-1] == ']' else ''


def map_object_literal(v: str | jsonasobj.JsonObj) -> ShExJ.ObjectLiteral:
    """ `PyShEx.jsg <https://github.com/hsolbrig/ShExJSG/ShExJSG/ShExJ.jsg>`_ does not add identifying
    types to ObjectLiterals.  This routine re-identifies the types
    """
    # TODO: isinstance(v, JSGString) should work here, but it doesn't with IRIREF(http://a.example/v1)
    return v if issubclass(type(v), JSGString) or (isinstance(v, JSGObject) and 'type' in v) else \
        ShExJ.IRIREF(v) if isinstance(v, str) else ShExJ.ObjectLiteral(**v._as_dict)
