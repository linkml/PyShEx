import re

from pyshex.parse_tree.parse_node import ParseNode
from pyshex.shape_expressions_language.p5_4_node_constraints import nodeSatisfiesStringFacet
from pyshex.shape_expressions_language.p5_context import Context
from tests.utils.setup_test import rdf_header, EX, setup_context


SHEX_1 = """{ "type": "Schema", "shapes": [
  { "id": "http://schema.example/IssueShape",
    "type": "Shape", "expression": {
      "type": "TripleConstraint",
      "predicate": "http://schema.example/submittedBy",
      "valueExpr": { "type": "NodeConstraint", "minlength": 10 } } } ] }
"""

SHEX_2 = """{ "type": "Schema", "shapes": [
  { "id": "http://schema.example/IssueShape",
    "type": "Shape", "expression": {
      "type": "TripleConstraint",
      "predicate": "http://schema.example/submittedBy",
      "valueExpr": { "type": "NodeConstraint",
                     "pattern": "genuser[0-9]+", "flags": "i" }
} } ] }"""

_pattern = re.sub(r'\\', r'\\\\', r'^\t\\𝒸\?$')
SHEX_3 = f"""{{ "type": "Schema", "shapes": [
  {{ "id": "http://schema.example/ProductShape",
    "type": "Shape", "expression": {{
      "type": "TripleConstraint",
      "predicate": "http://schema.example/trademark",
      "valueExpr": {{ "type": "NodeConstraint",
                     "pattern": "{_pattern}" }}
}} }} ] }}"""

RDF_1 = f"""{rdf_header}
:issue1 ex:submittedBy <http://a.example/bob> .
:issue2 ex:submittedOn "bob" ."""

RDF_2 = f"""{rdf_header}
:issue6 ex:submittedBy :genUser218 .
:issue7 ex:submittedBy :genContact817 ."""

# Warning: the tab in product6 must be preserved — spaces will break the match
RDF_3 = f"""{rdf_header}
:product6 ex:trademark "\\t\\\\𝒸?" .
:product7 ex:trademark "\\t\\\\\U0001D4B8?" .
:product8 ex:trademark "\\t\\\\\\\\U0001D4B8?" .
"""


def fail_reasons(cntxt: Context) -> list[str]:
    return [e.strip() for e in cntxt.current_node.fail_reasons(cntxt.graph)]


def test_string_facet_minlength() -> None:
    cntxt = setup_context(SHEX_1, RDF_1)
    nc = cntxt.schema.shapes[0].expression.valueExpr

    focus = cntxt.graph.value(EX.issue1, EX.submittedBy)
    cntxt.current_node = ParseNode(nodeSatisfiesStringFacet, nc, focus, cntxt)
    assert nodeSatisfiesStringFacet(cntxt, focus, nc)

    focus = cntxt.graph.value(EX.issue2, EX.submittedBy)
    cntxt.current_node = ParseNode(nodeSatisfiesStringFacet, nc, focus, cntxt)
    assert not nodeSatisfiesStringFacet(cntxt, focus, nc)
    assert fail_reasons(cntxt) == ['String length violation - minimum: 10 actual: 4']


def test_string_facet_pattern_with_flags() -> None:
    cntxt = setup_context(SHEX_2, RDF_2)
    nc = cntxt.schema.shapes[0].expression.valueExpr

    focus = cntxt.graph.value(EX.issue6, EX.submittedBy)
    cntxt.current_node = ParseNode(nodeSatisfiesStringFacet, nc, focus, cntxt)
    assert nodeSatisfiesStringFacet(cntxt, focus, nc)

    focus = cntxt.graph.value(EX.issue7, EX.submittedBy)
    cntxt.current_node = ParseNode(nodeSatisfiesStringFacet, nc, focus, cntxt)
    assert not nodeSatisfiesStringFacet(cntxt, focus, nc)
    assert fail_reasons(cntxt) == [
        'Pattern match failure - pattern: genuser[0-9]+ flags:i string: '
        'http://schema.example/genContact817'
    ]


def test_string_facet_unicode_pattern() -> None:
    cntxt = setup_context(SHEX_3, RDF_3)
    nc = cntxt.schema.shapes[0].expression.valueExpr

    focus = cntxt.graph.value(EX.product6, EX.trademark)
    cntxt.current_node = ParseNode(nodeSatisfiesStringFacet, nc, focus, cntxt)
    assert nodeSatisfiesStringFacet(cntxt, focus, nc)

    focus = cntxt.graph.value(EX.product7, EX.trademark)
    cntxt.current_node = ParseNode(nodeSatisfiesStringFacet, nc, focus, cntxt)
    assert nodeSatisfiesStringFacet(cntxt, focus, nc)

    focus = cntxt.graph.value(EX.product8, EX.trademark)
    cntxt.current_node = ParseNode(nodeSatisfiesStringFacet, nc, focus, cntxt)
    assert not nodeSatisfiesStringFacet(cntxt, focus, nc)
    assert fail_reasons(cntxt) == [
        'Pattern match failure - pattern: ^\\t\\\\𝒸\\?$ flags:None string: \t'
        '\\\\U0001D4B8?'
    ]