"""ShExMap binding functions: ``regex(...)`` and ``hashmap(...)``.

A ``%Map:{ ... %}`` action is either a variable name (``bp:given`` or ``<http://...>``),
which binds the matched value, or a function call.  Each function works in two
directions, as in shex.js's extension-map:

* **lift** runs while validating the input: it turns the matched value into bindings.
* **lower** runs while materializing the output: it turns bindings back into a value.

``regex(/(?<bp:family>[a-zA-Z]+), (?<bp:given>[a-zA-Z]+)/)``
    lift: match the value and bind each named group to the variable it names.
    lower: replace each named group with its variable's value, e.g. "Walker, Alice".

``hashmap(bp:status, {"D": "Divorced", "M": "Married"})``
    lift: bind the variable to the map's value for the matched key.
    lower: find the key whose value the variable holds.
"""
import json
import re
from collections.abc import Callable, Mapping

from rdflib import Literal
from rdflib.term import Node

VARIABLE = re.compile(r'^ *(?:<([^>]*)>|([^:<>\s]*):(\S*)) *$')
FUNCTION_CALL = re.compile(r'^\s*([A-Za-z][A-Za-z0-9]*)\s*\((.*)\)\s*$', re.S)
_CAPTURE_NAME = r'\?<((?:[A-Za-z0-9_.\-]*:[^>\s]*)|(?:<[^>]+>))>'


class MapFunctionError(ValueError):
    """A ShExMap function call is malformed or cannot be applied to its input."""


def expand_variable(name: str, prefixes: Mapping[str, str]) -> str:
    """Expand a ShExMap variable name -- ``prefix:local`` or ``<iri>`` -- to an IRI string."""
    m = VARIABLE.match(name)
    if not m:
        raise MapFunctionError(f'"{name}" is not a ShExMap variable (prefix:name or <iri>)')
    if m.group(1) is not None:
        return m.group(1)
    if m.group(2) not in prefixes:
        raise MapFunctionError(f'Unknown prefix "{m.group(2)}:" in ShExMap variable "{name}"')
    return prefixes[m.group(2)] + m.group(3)


def is_function_call(code: str) -> bool:
    return FUNCTION_CALL.match(code) is not None


def _split_call(code: str) -> tuple[str, str]:
    m = FUNCTION_CALL.match(code)
    if not m:
        raise MapFunctionError(f"Invalid ShExMap function call: {code.strip()}")
    return m.group(1), m.group(2)


def _lexical(value) -> str:
    return str(value)


def _collapse_spaces(s: str) -> str:
    return re.sub(r'  +', ' ', s)


def _unescape_meta(s: str) -> str:
    return re.sub(r'\\([/^$])', r'\1', s)


# -- regex -----------------------------------------------------------------------------

def _regex_body(code: str, args: str) -> str:
    m = re.match(r'^\s*/(.*)/\s*$', args, re.S)
    if m:
        args = m.group(1)
        if not args:
            raise MapFunctionError(f"{code.strip()} is missing the required regex pattern")
    return args


def _regex_lift(code: str, args: str, value, prefixes: Mapping[str, str]) -> dict[str, Node]:
    pattern = _regex_body(code, args)
    names: list[str] = []

    def unname(m: re.Match) -> str:
        names.append(expand_variable(_unescape_meta(m.group(1)), prefixes))
        return ''

    plain = re.sub(_CAPTURE_NAME, unname, pattern)
    if not names:
        raise MapFunctionError(f"Found no capture variable in {code.strip()}")
    try:
        found = re.search(plain, _lexical(value))
    except re.error as e:
        raise MapFunctionError(f"Error matching {code.strip()} against {_lexical(value)!r}: {e}") from e
    if not found:
        raise MapFunctionError(f'{code.strip()} found no match for input "{_lexical(value)}"')
    return {name: Literal(found.group(i + 1)) for i, name in enumerate(names)}


def _regex_lower(code: str, args: str, get: Callable[[str], Node | None], prefixes: Mapping[str, str]) -> Node | None:
    pattern = _regex_body(code, args)
    matched = False
    missing: list[str] = []

    def substitute(m: re.Match) -> str:
        nonlocal matched
        matched = True
        name = expand_variable(_unescape_meta(m.group(1)), prefixes)
        val = get(name)
        if val is None:
            missing.append(name)
            return ''
        return str(val)

    text = re.sub(r'\(' + _CAPTURE_NAME + r'[^)]+\)', substitute, pattern)
    if not matched:
        raise MapFunctionError(f"Found no capture variable in {code.strip()}")
    if missing:
        return None
    return Literal(_unescape_meta(_collapse_spaces(text)))


# -- hashmap ---------------------------------------------------------------------------

def _hashmap_args(code: str, args: str, prefixes: Mapping[str, str]) -> tuple[str, dict[str, str]]:
    m = re.match(r'^\s*([\w:<>/#.\-]+)\s*,\s*(\{.*\})\s*$', args, re.S)
    if not m:
        raise MapFunctionError(f"hashmap needs a variable name and a JSON map, found: {code.strip()}")
    try:
        mapping = json.loads(m.group(2))
    except json.JSONDecodeError as e:
        raise MapFunctionError(f"hashmap could not parse the map in {code.strip()}: {e}") from e
    if not isinstance(mapping, dict) or not mapping:
        raise MapFunctionError(f"hashmap needs a non-empty JSON object in {code.strip()}")
    if len(set(mapping.values())) != len(mapping):
        raise MapFunctionError(f"hashmap values must be unique so the map can be inverted: {code.strip()}")
    return expand_variable(m.group(1), prefixes), mapping


def _hashmap_lift(code: str, args: str, value, prefixes: Mapping[str, str]) -> dict[str, Node]:
    name, mapping = _hashmap_args(code, args, prefixes)
    key = _lexical(value)
    if key not in mapping:
        raise MapFunctionError(f'{code.strip()} has no entry for "{key}"')
    return {name: Literal(mapping[key])}


def _hashmap_lower(code: str, args: str, get: Callable[[str], Node | None], prefixes: Mapping[str, str]) -> Node | None:
    name, mapping = _hashmap_args(code, args, prefixes)
    val = get(name)
    if val is None:
        return None
    for key, mapped in mapping.items():
        if mapped == str(val):
            return Literal(key)
    raise MapFunctionError(f'{code.strip()} cannot invert "{val}"')


LIFTERS = {'regex': _regex_lift, 'hashmap': _hashmap_lift}
LOWERERS = {'regex': _regex_lower, 'hashmap': _hashmap_lower}


def lift(code: str, value, prefixes: Mapping[str, str]) -> dict[str, Node]:
    """Apply a function call to a matched value, returning the variable bindings it makes."""
    name, args = _split_call(code)
    if name not in LIFTERS:
        raise MapFunctionError(f"Unknown ShExMap function {name}() in {code.strip()}")
    return LIFTERS[name](code, args, value, prefixes)


def lower(code: str, get: Callable[[str], Node | None], prefixes: Mapping[str, str]) -> Node | None:
    """Build a value from bindings with a function call; None when a variable is unbound."""
    name, args = _split_call(code)
    if name not in LOWERERS:
        raise MapFunctionError(f"Unknown ShExMap function {name}() in {code.strip()}")
    return LOWERERS[name](code, args, get, prefixes)
