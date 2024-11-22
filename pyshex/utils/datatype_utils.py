import re
from typing import Optional, Tuple, Union

import jsonasobj
from ShExJSG import ShExJ
from pyjsg.jsglib import JSGString, JSGObject
from rdflib import Literal

from pyshex.sparql11_query.p17_1_operand_data_types import is_integer, is_numeric


def can_cast_to(v: Literal, dt: str) -> bool:
    """ 5.4.3 Datatype Constraints

    Determine whether "a value of the lexical form of n can be cast to the target type v per
    XPath Functions 3.1 section 19 Casting[xpath-functions]."
    """
    # TODO: rdflib doesn't appear to pay any attention to lengths (e.g. 257 is a valid XSD.byte)
    return v.value is not None and Literal(str(v), datatype=dt).value is not None


def total_digits(n: Literal) -> Optional[int]:
    """ 5.4.5 XML Schema Numeric Facet Constraints

     totaldigits and fractiondigits constraints on values not derived from xsd:decimal fail.
     """
    return len(str(abs(int(n.value)))) + fraction_digits(n) if is_numeric(n) and n.value is not None else None


def fraction_digits(n: Literal) -> Optional[int]:
    """ 5.4.5 XML Schema Numeric Facet Constraints

    for "fractiondigits" constraints, v is less than or equals the number of digits to the right of the decimal place
    in the XML Schema canonical form[xmlschema-2] of the value of n, ignoring trailing zeros.
    """
    # Note - the last expression below isolates the fractional portion, reverses it (e.g. 017320 --> 023710) and
    #        converts it to an integer and back to a string
    return None if not is_numeric(n) or n.value is None \
        else 0 if is_integer(n) or '.' not in str(n.value) or str(n.value).split('.')[1] == '0' \
        else len(str(int(str(n.value).split('.')[1][::-1])))


def pattern_match(pattern: str, flags: str, val: str) -> bool:
    re_flags, pattern = _map_xpath_flags_to_re(reencode_escapes(pattern), flags)
    return re.search(pattern, val, flags=re_flags) is not None


def reencode_escapes(pattern: str) -> str:
    return re.sub(r'\\.', _subf, pattern)


def _subf(matchobj) -> str:
    o = matchobj.group(0)
    return o if o[1] in ['\\', '^', '$', '?', ',', '[', ']', '(', ')'] \
        else '\t' if o[1] == 't' \
        else '\n' if o[1] == 'n' \
        else '\r' if o[1] == 'r' \
        else o[1]


def _map_xpath_flags_to_re(expr: str, xpath_flags: str) -> Tuple[int, str]:
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


def map_object_literal(v: Union[str, jsonasobj.JsonObj]) -> ShExJ.ObjectLiteral:
    """ `PyShEx.jsg <https://github.com/hsolbrig/ShExJSG/ShExJSG/ShExJ.jsg>`_ does not add identifying
    types to ObjectLiterals.  This routine re-identifies the types
    """
    # TODO: isinstance(v, JSGString) should work here, but it doesn't with IRIREF(http://a.example/v1)
    return v if issubclass(type(v), JSGString) or (isinstance(v, JSGObject) and 'type' in v) else \
        ShExJ.IRIREF(v) if isinstance(v, str) else ShExJ.ObjectLiteral(**v._as_dict)
