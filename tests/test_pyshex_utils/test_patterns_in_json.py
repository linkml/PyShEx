import json
import re


def test_non_unicode() -> None:
    """String facets example 2: non-unicode escape pattern round-trips through JSON."""
    b1 = '^\\t\\\\X\?$'
    b2 = r'^\t\\X\?$'

    assert b1 == b2
    assert re.search(b1, '\t\\X?') is not None
    assert re.search(b1, 'a\t\\X?') is None
    assert re.search(b1, '\t\\X?z') is None

    escaped_b1 = re.sub(r'\\', r'\\\\', b1)
    json_b1 = json.loads(f'{{"pattern" : "{escaped_b1}"}}')
    assert re.search(json_b1['pattern'], '\t\\X?') is not None


def test_unicode() -> None:
    """String facets example 2: unicode character pattern round-trips through JSON."""
    b1 = '^\\t\\\\𝒸\?$'
    b2 = r'^\t\\𝒸\?$'

    assert b1 == b2
    assert re.search(b1, '\t\\𝒸?') is not None
    assert re.search(b1, 'a\t\\𝒸?') is None
    assert re.search(b1, '\t\\𝒸?z') is None

    escaped_b1 = re.sub(r'\\', r'\\\\', b1)
    json_b1 = json.loads(f'{{"pattern" : "{escaped_b1}"}}')
    assert re.search(json_b1['pattern'], '\t\\𝒸?') is not None


def test_unicode_escape() -> None:
    """String facets example 2: unicode escape sequence pattern round-trips through JSON."""
    b1 = '^\\t\\\\\U0001D4B8\?$'
    b2 = r'^\t\\𝒸\?$'

    assert b1 == b2
    assert re.search(b1, '\t\\\U0001D4B8?') is not None
    assert re.search(b1, 'a\t\\\U0001D4B8?') is None
    assert re.search(b1, '\t\\\U0001D4B8?z') is None

    escaped_b1 = re.sub(r'\\', r'\\\\', b1)
    json_b1 = json.loads(f'{{"pattern" : "{escaped_b1}"}}')
    assert re.search(json_b1['pattern'], '\t\\\U0001D4B8?') is not None